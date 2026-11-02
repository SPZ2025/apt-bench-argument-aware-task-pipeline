"""Argument-aware task v1.1. File jobs run in separate agent contexts; no API keys."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DIMENSIONS = ('executability', 'mainline_retention', 'abstraction', 'leakage_safety', 'field_nonredundancy')
FIELDS = ('schema_version','writing_goal','central_question','argumentative_throughline','conceptual_scope','constraints')
TERMINAL = {'approved','ineligible','needs_human_review'}
TOKENIZER = Path.home()/'.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots/614241f622f53c4eeff9890bdc4f31cfecc418b3/tokenizer.json'

def require(ok, message):
    if not ok: raise ValueError(message)

def canonical(x): return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False)
def digest(x): return hashlib.sha256(canonical(x).encode()).hexdigest()
def file_sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def pairs(items):
    result={}
    for k,v in items:
        require(k not in result, 'Duplicate JSON key: '+k); result[k]=v
    return result
def decode(s):
    return json.loads(s, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
def read(p): return decode(Path(p).read_text(encoding='utf-8-sig'))
def rows(p): return [decode(s) for s in Path(p).read_text(encoding='utf-8-sig').splitlines() if s.strip()]
def write(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8');tmp.replace(p)
def jsonl(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(''.join(canonical(v)+'\n' for v in x),encoding='utf-8');tmp.replace(p)
def string(x): require(isinstance(x,str) and bool(x.strip()),'Expected nonempty string')
def exact(x,keys): require(isinstance(x,dict) and set(x)==set(keys),'Unexpected/missing fields: '+str(keys))
def strings(x):
    require(isinstance(x,list),'Expected array')
    for v in x: string(v)
    require(len(x)==len(set(x)),'Duplicate array items')

def validate_task(t):
    exact(t,FIELDS);require(t['schema_version']=='apt_task_v1_1','Wrong Task version')
    for k in FIELDS[1:4]:string(t[k])
    for k in FIELDS[4:]:strings(t[k])

def validate_map(m,source):
    exact(m,('central_problem','central_claim','major_components','relations','discourse_functions','central_trajectory','potential_leakage'))
    string(m['central_problem']);string(m['central_trajectory'])
    if m['central_claim'] is not None:string(m['central_claim'])
    strings(m['discourse_functions']);strings(m['potential_leakage'])
    require(isinstance(m['major_components'],list) and bool(m['major_components']),'Missing major components')
    ids=[]
    for c in m['major_components']:
        exact(c,('id','role','content','centrality','evidence_quote'))
        for k in c:string(c[k])
        require(c['role'] in ('claim','premise','objection','qualification','definition','question','observation'),'Invalid component role')
        require(c['centrality'] in ('core','peripheral'),'Invalid centrality')
        require(c['evidence_quote'] in source,'Evidence quote must occur verbatim in this source')
        ids.append(c['id'])
    require(len(ids)==len(set(ids)),'Duplicate component IDs')
    require(isinstance(m['relations'],list),'Invalid relations')
    seen=set()
    for r in m['relations']:
        exact(r,('source','target','type'));require(r['source'] in ids and r['target'] in ids and r['source']!=r['target'],'Dangling/self relation')
        require(r['type'] in ('support','challenge','qualification','explanation','implication'),'Invalid relation type')
        key=canonical(r);require(key not in seen,'Duplicate relation');seen.add(key)

def validate_analysis(x,source):
    exact(x,('eligibility','argument_map'));e=x['eligibility'];exact(e,('status','reason'));string(e['reason'])
    require(e['status'] in ('eligible','ineligible','needs_human_review'),'Invalid eligibility')
    if e['status']=='eligible':validate_map(x['argument_map'],source)
    else:require(x['argument_map'] is None,'Ineligible input cannot have a map')

def validate_audit(x):
    exact(x,('review','high_risk_leakage','repair_target'));r=x['review']
    exact(r,('decision','scores','reason','revision_request'));exact(r['scores'],DIMENSIONS)
    require(r['decision'] in ('approve','revise'),'Invalid audit decision');string(r['reason'])
    require(all(type(v) is int and 1<=v<=5 for v in r['scores'].values()),'Scores must be integers 1–5')
    require(type(x['high_risk_leakage']) is bool,'Leakage flag must be boolean')
    require(x['repair_target'] in (None,'task','argument_map'),'Invalid repair target')
    if r['decision']=='revise':
        string(r['revision_request']);require(x['repair_target'] is not None,'Revision needs repair target')
    else:require(r['revision_request'] is None,'Approved review must have null revision_request')

def acceptable(x):
    validate_audit(x)
    return x['review']['decision']=='approve' and all(v>=4 for v in x['review']['scores'].values()) and not x['high_risk_leakage'] and x['repair_target'] is None

def token_count(text, tokenizer):
    from tokenizers import Tokenizer
    return len(Tokenizer.from_file(str(tokenizer)).encode(text,add_special_tokens=False).ids)

def init_run(source,run,limit=3,tokenizer=TOKENIZER):
    source=Path(source).resolve();run=Path(run).resolve();tokenizer=Path(tokenizer).resolve()
    require(not run.exists(),'Run directory exists; choose a new run')
    require(type(limit) is int and limit>0,'Positive explicit input limit required')
    require(tokenizer.is_file(),'Existing E5 tokenizer missing; do not download/install')
    selected=rows(source)[:limit];require(bool(selected),'No input records')
    units_path=source.parent/'source_units.jsonl'
    units={u['unit_id']:u for u in rows(units_path)} if units_path.exists() else None
    # Aggregate corpus files have per-author source files rather than one global file.
    sources=[]; records=[];seen=set()
    for i,row in enumerate(selected,1):
        text=row.get('source_text',row.get('text'));string(text)
        identity=(row.get('scholar_id'),row.get('fragment_id',row.get('sample_id',row.get('candidate_id'))))
        require(identity not in seen,'Duplicate input identity');seen.add(identity)
        authority=units
        ap=source.parent/'authors'/str(row.get('scholar_id'))/'source_units.jsonl'
        if authority is None and ap.exists():authority={u['unit_id']:u for u in rows(ap)}
        if row.get('source_spans'):
            require(authority is not None and row.get('unit_id') in authority,'Cannot verify supplied source coordinates')
            require(text==''.join(authority[row['unit_id']]['text'][a:b] for a,b in row['source_spans']),'Source reconstruction mismatch')
        sid=f'F{i:06d}';n=token_count(text,tokenizer)
        sources.append({'fragment_id':sid,'source_text':text,'source_sha256':digest(text),'token_count':n,
                        'length_note':None if 1200<=n<=3000 else 'Outside inherited 1200–3000 band; semantic eligibility still required',
                        'provenance':{k:v for k,v in row.items() if k not in ('text','source_text','context','paragraph')}})
        records.append({'fragment_id':sid,'status':'analyze','revision':0,'map':None,'task':None,'feedback':None,'job_id':None})
    frozen={}
    for path in [ROOT/'pipeline.py',ROOT/'methodology.md',*sorted((ROOT/'prompts').glob('*.md')),*sorted((ROOT/'schemas').glob('*.json'))]:
        relative=str(path.relative_to(ROOT));target=run/'protocol'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target);frozen[relative]=file_sha(path)
    jsonl(run/'private/sources.jsonl',sources)
    manifest={'version':'argument_aware_pipeline_1.1','created_at':now(),'source_path':str(source),'source_file_sha256':file_sha(source),
              'frozen_source_sha256':file_sha(run/'private/sources.jsonl'),'tokenizer':{'path':str(tokenizer),'sha256':file_sha(tokenizer),'add_special_tokens':False},
              'protocol_files':frozen,'max_revisions':2,'score_threshold':4,'input_limit':limit,'input_count':len(records),
              'execution':'separate fresh-context agent jobs; model/actor recorded on submission'}
    write(run/'manifest.json',manifest);write(run/'private/state.json',{'records':records,'jobs':[],'events':[]})
    export(run);return {'run':str(run),'inputs':len(records)}

def load_run(run):
    run=Path(run).resolve();m=read(run/'manifest.json')
    require(file_sha(run/'private/sources.jsonl')==m['frozen_source_sha256'],'Frozen sources changed')
    require(file_sha(Path(m['tokenizer']['path']))==m['tokenizer']['sha256'],'Tokenizer changed')
    for name,sha in m['protocol_files'].items():require(file_sha(run/'protocol'/name)==sha,'Frozen protocol changed: '+name)
    require(file_sha(ROOT/'pipeline.py')==m['protocol_files']['pipeline.py'],'Runner changed; create a new run or use frozen runner')
    return run,m,read(run/'private/state.json'),{r['fragment_id']:r for r in rows(run/'private/sources.jsonl')}

def next_job(run):
    run,m,s,sources=load_run(run)
    active=next((j for j in s['jobs'] if j['status']=='pending'),None)
    if active:return {'action':'agent_job','job_path':active['path']}
    r=next((r for r in s['records'] if r['status'] not in TERMINAL),None)
    if r is None:return {'action':'complete','counts':dict(__import__('collections').Counter(r['status'] for r in s['records']))}
    stage=r['status'];sid=r['fragment_id'];jid=f'J{len(s["jobs"])+1:06d}'
    if stage=='analyze':
        payload={'source_text':sources[sid]['source_text']}
        if r['feedback']:payload['map_correction_request']=r['feedback']
    elif stage=='construct':payload={'argument_map':r['map']}
    elif stage=='revise':payload={'argument_map':r['map'],'current_task':r['task'],'revision_request':r['feedback']}
    elif stage=='audit':payload={'source_text':sources[sid]['source_text'],'task':r['task']}
    else:raise ValueError('Unknown stage')
    prompt=(run/'protocol/prompts'/f'{stage}.md').read_text(encoding='utf-8')
    packet={'job_id':jid,'stage':stage,'prompt':prompt,'payload':payload,
            'response_contract': 'Return {job_id,input_hash,result}; result follows the prompt. No Markdown.',
            'output_path':str(run/'responses'/f'{jid}.json')}
    packet['input_hash']=digest(packet)
    path=run/'jobs'/f'{jid}.json';write(path,packet)
    s['jobs'].append({'job_id':jid,'fragment_id':sid,'stage':stage,'revision':r['revision'],'status':'pending',
                      'path':str(path),'packet_sha256':file_sha(path),'input_hash':packet['input_hash']})
    r['job_id']=jid;write(run/'private/state.json',s)
    return {'action':'agent_job','job_path':str(path)}

def submit(run,job_id,response,actor,model):
    run,m,s,sources=load_run(run);string(actor);string(model)
    j=next(j for j in s['jobs'] if j['job_id']==job_id)
    require(j['status']=='pending','Job already submitted')
    require(all(old.get('actor')!=actor for old in s['jobs']),'Use a fresh-context actor for every call')
    require(file_sha(j['path'])==j['packet_sha256'],'Issued packet changed')
    raw=Path(response).read_text(encoding='utf-8-sig');raw_sha=hashlib.sha256(raw.encode()).hexdigest()
    r=next(r for r in s['records'] if r['fragment_id']==j['fragment_id']);require(r['job_id']==job_id and r['status']==j['stage'],'Stale assignment')
    try:
        envelope=decode(raw);exact(envelope,('job_id','input_hash','result'))
        require(envelope['job_id']==job_id and envelope['input_hash']==j['input_hash'],'Response binding mismatch')
        x=envelope['result'];stage=j['stage']
        if stage=='analyze':validate_analysis(x,sources[r['fragment_id']]['source_text'])
        elif stage in ('construct','revise'):validate_task(x)
        else:validate_audit(x)
    except (ValueError,KeyError,TypeError) as exc:
        rejected=run/'private/rejected'/f'{job_id}_{raw_sha}.txt';rejected.parent.mkdir(parents=True,exist_ok=True);rejected.write_text(raw,encoding='utf-8')
        s['events'].append({'job_id':job_id,'fragment_id':r['fragment_id'],'status':'invalid_response','reason':str(exc),'response_sha256':raw_sha,'at':now()})
        write(run/'private/state.json',s);export(run);raise ValueError('Response rejected without state advancement: '+str(exc)) from exc
    receipt={'job_id':job_id,'fragment_id':r['fragment_id'],'stage':stage,'revision':r['revision'],'actor':actor,'model':model,'at':now(),
             'source_sha256':sources[r['fragment_id']]['source_sha256'],'input_hash':j['input_hash'],'result':x}
    if stage=='audit':receipt['task_sha256']=digest(r['task'])
    write(run/'private/receipts'/f'{job_id}.json',receipt)
    if stage=='analyze':
        r['eligibility']=x['eligibility'];r['map']=x['argument_map']
        r['status']='construct' if x['eligibility']['status']=='eligible' else x['eligibility']['status']
    elif stage in ('construct','revise'):r['task']=x;r['status']='audit'
    elif acceptable(x):r['status']='approved';r['approved_receipt']=job_id
    elif r['revision']>=m['max_revisions']:r['status']='needs_human_review';r['feedback']=x['review']['reason']
    else:
        r['revision']+=1;r['feedback']=x['review']['revision_request'] or x['review']['reason']
        r['status']='analyze' if x['repair_target']=='argument_map' else 'revise'
        if r['status']=='analyze':r['map']=None;r['task']=None
    j.update(status='done',actor=actor,model=model,response_sha256=raw_sha,receipt_sha256=file_sha(run/'private/receipts'/f'{job_id}.json'))
    r['job_id']=None;s['events'].append({'job_id':job_id,'fragment_id':r['fragment_id'],'status':r['status'],'at':now()})
    write(run/'private/state.json',s);export(run);return {'job_id':job_id,'status':r['status'],'revision':r['revision']}

def export(run):
    run,m,s,sources=load_run(run);tasks=[];mapping=[]
    receipts=[]
    for job in s['jobs']:
        if job['status']=='done':
            path=run/'private/receipts'/f'{job["job_id"]}.json'
            require(file_sha(path)==job['receipt_sha256'],'Stored model result changed')
            receipts.append(read(path))
    for r in s['records']:
        if r['status']!='approved':continue
        validate_task(r['task']);receipt=next(x for x in receipts if x['job_id']==r['approved_receipt'])
        require(acceptable(receipt['result']) and receipt['task_sha256']==digest(r['task']),'Approval/task mismatch')
        tasks.append(r['task']);mapping.append({'fragment_id':r['fragment_id'],'task_line':len(tasks),'task_sha256':digest(r['task']),
                                             'source_sha256':sources[r['fragment_id']]['source_sha256'],'audit_job_id':receipt['job_id']})
    jsonl(run/'outputs/tasks.jsonl',tasks)
    jsonl(run/'private/task_index.jsonl',mapping)
    jsonl(run/'private/argument_maps.jsonl',[x for x in receipts if x['stage']=='analyze'])
    jsonl(run/'private/audit.jsonl',[x for x in receipts if x['stage']=='audit'])
    jsonl(run/'private/failed.jsonl',[{'fragment_id':r['fragment_id'],'status':r['status'],'reason':r.get('feedback') or r.get('eligibility',{}).get('reason')} for r in s['records'] if r['status'] in TERMINAL-{'approved'}]+[x for x in s['events'] if x['status']=='invalid_response'])
    write(run/'progress.json',{'input_count':len(s['records']),'approved':len(tasks),'states':{r['fragment_id']:r['status'] for r in s['records']}})

def main():
    parser=argparse.ArgumentParser();subs=parser.add_subparsers(dest='command',required=True)
    init=subs.add_parser('init');init.add_argument('--source',type=Path,required=True);init.add_argument('--run',type=Path,required=True);init.add_argument('--limit',type=int,default=3);init.add_argument('--tokenizer',type=Path,default=TOKENIZER)
    for name in ('next','export','submit'):
        cmd=subs.add_parser(name);cmd.add_argument('--run',type=Path,required=True)
        if name=='submit':
            for arg in ('job','response','actor','model'):cmd.add_argument('--'+arg,required=True)
    a=parser.parse_args()
    if a.command=='init':result=init_run(a.source,a.run,a.limit,a.tokenizer)
    elif a.command=='next':result=next_job(a.run)
    elif a.command=='export':export(a.run);result={'status':'exported'}
    else:result=submit(a.run,a.job,a.response,a.actor,a.model)
    print(canonical(result))

if __name__=='__main__':main()
