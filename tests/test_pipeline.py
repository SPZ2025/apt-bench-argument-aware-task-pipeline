import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pipeline as p

SOURCE='A rule can preserve coordination. Uniform rules may also limit adaptation.'
TASK=dict(schema_version='apt_task_v1_1',writing_goal='Assess institutional rules.',central_question='When should rules be uniform?',argumentative_throughline='Relate coordination requirements to the scope for contextual adaptation.',conceptual_scope=['coordination','adaptation'],constraints=[])
MAP=dict(central_problem='How do rules balance coordination and adaptation?',central_claim=None,
         major_components=[dict(id='A1',role='observation',content='Rules support coordination.',centrality='core',evidence_quote='A rule can preserve coordination.')],
         relations=[],discourse_functions=['conceptual_clarification'],central_trajectory='Consider coordination alongside adaptation.',potential_leakage=[])
ANALYSIS=dict(eligibility=dict(status='eligible',reason='Readable discussion.'),argument_map=MAP)
AUDIT=dict(review=dict(decision='approve',scores={k:4 for k in p.DIMENSIONS},reason='TEST FIXTURE ONLY',revision_request=None),high_risk_leakage=False,repair_target=None)

class FlowTests(unittest.TestCase):
    def setUp(self):
        temp_root=p.ROOT/'runs'/'_tests';temp_root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=temp_root);self.base=Path(self.tmp.name).resolve()
        assert self.base.is_relative_to(temp_root.resolve())
        self.addCleanup(self.tmp.cleanup)
        src=self.base/'input.jsonl';p.jsonl(src,[dict(fragment_id='original1',source_text=SOURCE,author='secret_author')]);token=self.base/'tokenizer.json';token.write_text('{}')
        self.run=self.base/'run'
        with patch.object(p,'token_count',return_value=1250):p.init_run(src,self.run,1,token)
    def job(self):return p.read(p.next_job(self.run)['job_path'])
    def send(self,result,actor=None):
        j=self.job();out=self.base/'response.json';p.write(out,dict(job_id=j['job_id'],input_hash=j['input_hash'],result=result))
        return p.submit(self.run,j['job_id'],out,actor or j['job_id'],'test-fixture-not-a-model')
    def ready_audit(self):self.send(ANALYSIS);self.send(TASK)
    def test_happy_path_and_pure_export(self):
        self.ready_audit();self.send(AUDIT)
        self.assertEqual(p.next_job(self.run)['action'],'complete')
        self.assertEqual(p.rows(self.run/'outputs/tasks.jsonl'),[TASK])
        index=p.rows(self.run/'private/task_index.jsonl')[0]
        self.assertEqual(index['task_line'],1);self.assertEqual(index['task_sha256'],p.digest(TASK))
    def test_payload_separation(self):
        first=self.job();self.assertEqual(set(first['payload']),{'source_text'})
        self.send(ANALYSIS);second=self.job();self.assertEqual(set(second['payload']),{'argument_map'})
        self.assertNotIn('secret_author',p.canonical(second))
        self.send(TASK);audit=self.job();self.assertEqual(set(audit['payload']),{'source_text','task'})
        self.assertNotIn('argument_map',audit['payload']);self.assertNotIn('scores',audit['payload'])
    def test_pending_job_stable(self):self.assertEqual(self.job(),self.job())
    def test_task_extra_whitespace_duplicate_items(self):
        for field,value in [('reasoning_requirements',[]),('writing_goal','  '),('constraints',['x','x'])]:
            t=copy.deepcopy(TASK);t[field]=value
            with self.assertRaises(ValueError):p.validate_task(t)
    def test_map_grounding_and_links(self):
        m=copy.deepcopy(MAP);m['major_components'][0]['evidence_quote']='Invented evidence'
        with self.assertRaises(ValueError):p.validate_map(m,SOURCE)
    def test_map_uses_exact_array_types_and_relation_enums(self):
        m=copy.deepcopy(MAP);m['discourse_functions']=[{'function':'clarification'}]
        with self.assertRaises(ValueError):p.validate_map(m,SOURCE)
        m=copy.deepcopy(MAP);c=copy.deepcopy(m['major_components'][0]);c['id']='A2';m['major_components'].append(c)
        m['relations']=[dict(source='A1',target='A2',type='supports')]
        with self.assertRaises(ValueError):p.validate_map(m,SOURCE)
        m=copy.deepcopy(MAP);m['relations']=[dict(source='A1',target='missing',type='support')]
        with self.assertRaises(ValueError):p.validate_map(m,SOURCE)
    def test_duplicate_keys_nan(self):
        for text in ['{"a":1,"a":2}','{"a":NaN}']:
            with self.assertRaises(ValueError):p.decode(text)
    def test_score_and_leakage_veto(self):
        for change in ('low','leakage'):
            review=copy.deepcopy(AUDIT)
            if change=='low':review['review']['scores']['field_nonredundancy']=3
            else:review['high_risk_leakage']=True
            self.assertFalse(p.acceptable(review))
    def test_effective_veto_routes_revision(self):
        self.ready_audit();a=copy.deepcopy(AUDIT);a['high_risk_leakage']=True
        self.assertEqual(self.send(a)['status'],'revise');self.assertEqual(p.rows(self.run/'outputs/tasks.jsonl'),[])
    def test_map_error_returns_to_analysis(self):
        self.ready_audit();a=copy.deepcopy(AUDIT);a['review'].update(decision='revise',revision_request='The central question was misidentified.');a['repair_target']='argument_map'
        self.send(a);j=self.job();self.assertEqual(j['stage'],'analyze');self.assertNotIn('current_task',j['payload'])
    def test_two_revisions_and_full_reaudit(self):
        self.ready_audit();a=copy.deepcopy(AUDIT);a['review'].update(decision='revise',revision_request='Too detailed.');a['repair_target']='task'
        for revision in range(2):
            self.send(a);self.assertEqual(self.job()['stage'],'revise');self.send(TASK)
            self.assertEqual(set(self.job()['payload']),{'source_text','task'})
        self.assertEqual(self.send(a)['status'],'needs_human_review');self.assertEqual(p.rows(self.run/'outputs/tasks.jsonl'),[])
    def test_ineligible_skips_task(self):
        self.send(dict(eligibility=dict(status='ineligible',reason='Not academic discussion.'),argument_map=None))
        self.assertEqual(p.next_job(self.run)['action'],'complete');self.assertEqual(len(p.rows(self.run/'private/failed.jsonl')),1)
    def test_response_binding_and_recovery(self):
        j=self.job();out=self.base/'bad.json';p.write(out,dict(job_id=j['job_id'],input_hash='stale',result=ANALYSIS))
        with self.assertRaises(ValueError):p.submit(self.run,j['job_id'],out,'a','test')
        self.assertEqual(self.job()['job_id'],j['job_id']);self.send(ANALYSIS)
        self.assertTrue(p.rows(self.run/'private/failed.jsonl'))
    def test_actor_reuse_rejected(self):
        self.send(ANALYSIS,actor='same')
        with self.assertRaises(ValueError):self.send(TASK,actor='same')
    def test_protocol_and_receipt_tampering(self):
        self.send(ANALYSIS);path=next((self.run/'private/receipts').glob('*.json'));path.write_text('{}')
        with self.assertRaises(ValueError):p.export(self.run)
    def test_multi_input_export_mapping_not_source_position(self):
        other=self.base/'two.jsonl';p.jsonl(other,[dict(fragment_id='bad',text=SOURCE),dict(fragment_id='good',text=SOURCE)])
        run=self.base/'two'
        with patch.object(p,'token_count',return_value=1250):p.init_run(other,run,2,self.base/'tokenizer.json')
        self.run=run;self.send(dict(eligibility=dict(status='ineligible',reason='fixture'),argument_map=None))
        self.ready_audit();self.send(AUDIT)
        index=p.rows(run/'private/task_index.jsonl');self.assertEqual(index[0]['fragment_id'],'F000002');self.assertEqual(index[0]['task_line'],1)

if __name__=='__main__':unittest.main()
