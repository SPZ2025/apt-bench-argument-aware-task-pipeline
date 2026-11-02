# APT-Bench 长文本 Task 逆向生成方法规范（Argument-Aware v1.1）

> **用途**：作为独立 GPT 项目的实施规范，从学术 Fragment 批量构造、审核并保存结构化 Task。  
> **范围**：只做 Task 生成，不包括执行 Task、生成学术文本、模型微调或新一轮实验。  
> **输入**：原则上 1500–3000 tokens 的学术论述 Fragment；以原项目的 tokenizer 和 eligibility 标准为准。  
> **输出**：审核通过的 `apt_task_v1_1` JSON，及单独保存的内部审计记录。

## 1. 目标与原则

给定真实学术文本 \(F\)，逆向构造一个可以独立执行的学术写作 Task \(T\)。Task 应保留原文的**抽象论证主线**（abstract argumentative through-line），而不是成为摘要、段落提纲或原文独特论证的重建说明。

合格 Task 须同时满足：① 核心写作目标清楚；② 问题自足、结论开放；③ 体现总体层级的论证推进关系；④ 不泄露原文特定结论、证据组合和推导步骤；⑤ 字段职责互不重复；⑥ 可结构化校验与独立审核。

**方法概览**：

```text
Source Fragment
   │
   ▼
[Prompt 1] Lightweight Argument Mining + Discourse Analysis
   │ 内部 Argument Map
   ▼
[Prompt 2] Answer-Neutral Abstraction + Structured Task
   │ 五实质字段的 apt_task_v1_1 JSON
   ▼
[Prompt 3] Independent Audit
   ├─ approve → Schema 校验 → tasks.jsonl
   └─ revise → 定向修订 → 复审
                    └─ 仍不通过 → needs_human_review
```

默认使用三次独立 GPT 调用，分别分析、构造和审核。只有审核未通过时才追加修订调用。Argument Mining 是**借鉴的分析思想**，不是要求训练或部署专用模型。

## 2. 学术依据与适用边界

以下均为已发表论文，链接指向官方论文页：

1. **Köksal et al. (2024), [LongForm: Effective Instruction Tuning with Reverse Instructions](https://aclanthology.org/2024.findings-emnlp.414/), Findings of EMNLP 2024**：从人类写作文本反向产生 Instruction。借鉴“先有原文、再逆向构造任务”的基本范式。
2. **Li et al. (2024), [Self-Alignment with Instruction Backtranslation](https://proceedings.iclr.cc/paper_files/paper/2024/hash/0f8e3534eb8dee7478d4dc0e9d9a0b1a-Abstract-Conference.html), ICLR 2024**：将候选指令构造和质量筛选分离。借鉴独立审核的流程思想，不使用其训练/自对齐环节。
3. **Chen et al. (2024), [REInstruct: Building Instruction Data from Unlabeled Corpus](https://aclanthology.org/2024.findings-acl.408/), Findings of ACL 2024**：在逆向构造之前筛选合适文本。借鉴源文资格审查，不使用其响应重写训练环节。
4. **Stab & Gurevych (2017), [Parsing Argumentation Structures in Persuasive Essays](https://aclanthology.org/J17-3005/), *Computational Linguistics* 43(3)**：区分论证成分及其支持、反驳关系。借鉴内部结构化分析，不直接移植其议论文标签体系到所有学科。

**本项目自己作出的设计决策**：使用轻量级 Argument Map；内部同时理解论证关系与篇章功能；对原文论证做去答案化压缩；把 `argumentative_throughline` 作为核心字段；删除与之重复的 `reasoning_requirements`；单独审查字段冗余和内容泄漏。这些并不是上述论文已经证明有效的 Schema。

2026-10-25 Pilot 的小规模模型盲评显示：主线驱动 Task 的平均结构相似性高于主题驱动 Task（3.50 vs. 2.42，1–5 分），但泄漏安全性较低（4.33 vs. 5.00），初始任务有 5/12 需要修订；生成质量接近评分上限且没有人工验证。此后实践又发现 `reasoning_requirements` 与主线字段重复。因此，本规范以**抽象主线 + 独立审核 + 非冗余 Schema**为工程默认方案，不声称经大规模验证。

## 3. 输入资格与数据隔离

输入为单个 Fragment 的正文及受控内部标识。项目应：

- 冻结源文本，记录 `fragment_id`、文本哈希、tokenizer、token 数；
- 用原项目资格规则判断文本是否可独立分析；乱码、明显截断、无可恢复中心问题者进入人工复核或不合格集合；
- 不把作者、作品标题、引文出处、内部 ID 写入最终 Task；
- 不将其他来源文本或当前作者其他作品混入本条样本上下文；
- 对历史性的歧视性、优生学或未经证实的主张，以**作者的主张**分析其论证角色，不转化为事实前提。

内部分析与审计数据可保留源文细节，但最终 Task 必须与这些信息分离。

## 4. Prompt 1：Argument Mining + Discourse Analysis

### 4.1 任务

识别与**中心问题**相关的少量重要论证元素，而不是逐段摘要或穷举全部句子。

内部需要辨别：

- `central_problem`：核心知识问题；
- `central_claim`：核心主张，若文本未提出确定主张则为 `null`；
- `major_components`：主要主张、理由、异议和限定；每个成分须能找到文本依据；
- `relations`：主要成分之间的支持、质疑、解释、限定或推论关系；
- `discourse_functions`：如问题界定、概念澄清、历史类比、机制解释、规范性讨论等（不必强行变成 claim–premise）；
- `central_trajectory`：主要论证依赖的总体轨迹；
- `potential_leakage`：原文特有的结论、例子和推理细节，用于提醒下一阶段删除。

**内部建议格式**（不是最终 Task）：

```json
{
  "central_problem": "string",
  "central_claim": null,
  "major_components": [
    {
      "id": "A1",
      "role": "claim",
      "content": "string",
      "centrality": "core"
    }
  ],
  "relations": [
    {
      "source": "A1",
      "target": "A2",
      "type": "support"
    }
  ],
  "discourse_functions": ["problem_framing"],
  "central_trajectory": "string",
  "potential_leakage": ["string"]
}
```

`source` / `target` 必须引用真实存在的成分 ID，且关系方向需要有明确约定；上面的 ID 仅示意，实际输出不能出现悬空引用。关系类型 `support`、`challenge`、`qualification`、`explanation`、`implication` 是本项目扩展的分析标签，并非全部来自 Stab & Gurevych 的原始标签体系。文本相邻不等于逻辑依赖，证据不足时允许省略关系。

### 4.2 Prompt 1（可复制）

```text
You are an academic argument analyst for APT-Bench.

Input: one academic source fragment.
Your only output is an INTERNAL argument map. Do not generate a writing task
or write a new academic passage.

Identify the central intellectual problem; a central claim if there is one;
a small set of major claims, premises, objections and qualifications;
the important supported relations among them; and relevant discourse
functions (such as conceptual clarification, problem framing, analogy,
mechanism explanation, normative evaluation).

Distinguish argumentative dependencies from paragraph order, and core
components from peripheral examples. Do not turn every paragraph into
a separate requirement or infer causality from adjacency.

Summarize the central argumentative trajectory and explicitly list
source-specific claims, distinctive examples, evidence combinations
and inferential details that must NOT be exposed in a downstream task.

Treat controversial or historical assertions as claims made by the source,
not as established facts. Do not introduce external claims.

Output one valid JSON argument map with:
central_problem, central_claim, major_components, relations,
discourse_functions, central_trajectory, potential_leakage.
```

## 5. Prompt 2：抽象论证主线 → 结构化 Task

### 5.1 操作性规则

第二阶段只读取内部 Argument Map，默认不直接读取原文全文，降低重新引入细节的机会。若 Map 错误或缺少定义核心问题所必需的信息，应回到 Prompt 1 修订。

按以下对应关系完成转换：

| 内部分析 | 最终字段 | 转换方式 |
|---|---|---|
| 中心思想工作 | `writing_goal` | 说明**要做什么**，不是重复主线步骤 |
| 核心问题或中心主张 | `central_question` | 改写为**答案开放**的研究问题 |
| 关键论证依赖与篇章推进 | `argumentative_throughline` | 压缩为**一条宏观逻辑推进描述** |
| 必要概念与对象 | `conceptual_scope` | 仅列名词性概念，不写指令或步骤 |
| 不可省略的适用边界 | `constraints` | 只填特殊边界；通常允许 `[]` |

**刻意删除 `reasoning_requirements`**：抽象论证动作已经由 `argumentative_throughline` 统一承担，不再分散到第二个字段。

一个合格的 `argumentative_throughline` 既不应空泛到适用于任意文章，也不应详细到可以还原原文各个论证环节。其作用是描述**核心问题与总体分析、评价或规范性判断之间的逻辑关系**，不是完整论证图、结论摘要或段落大纲。

### 5.2 Prompt 2（可复制）

```text
You construct an apt_task_v1_1 structured writing task from an INTERNAL
argument map. Do not write the target essay.

Goal: retain the ABSTRACT argumentative through-line while preserving
task executability and leaving the answer open.

1. writing_goal: WHAT intellectual work is being requested?
2. central_question: WHICH self-contained, open question is addressed?
3. argumentative_throughline: HOW does the inquiry develop at the level
   of broad logical dependencies? Do not copy the detailed source path.
4. conceptual_scope: WHICH indispensable concepts delimit the topic?
   Use concepts, not imperatives or restatements of the through-line.
5. constraints: WHICH task-specific boundaries are indispensable?
   Use [] if none are needed.

Remove source-specific conclusions, evidence, unusual examples, named
sources, distinctive counterarguments, and detailed inferential steps.
Do not prescribe the source's answer or paragraph sequence.
Keep writing_goal and argumentative_throughline nonredundant.
Do not add a reasoning_requirements field or generic boilerplate.
Do not refer to the original author or require stylistic imitation.

Return exactly one valid JSON object with the six keys:
schema_version, writing_goal, central_question,
argumentative_throughline, conceptual_scope, constraints.
Set schema_version to "apt_task_v1_1".
No Markdown fences, explanations or extra fields.
```

## 6. 最终 Schema：`apt_task_v1_1`

**最终格式**为五个实质字段 + 一个版本字段：

```json
{
  "schema_version": "apt_task_v1_1",
  "writing_goal": "string",
  "central_question": "string",
  "argumentative_throughline": "string",
  "conceptual_scope": ["string"],
  "constraints": ["string"]
}
```

字段职责必须严格分离：`writing_goal` 是学术任务目标；`central_question` 是开放问题；`argumentative_throughline` 是总体论证推进；`conceptual_scope` 是概念边界；`constraints` 是任务特有约束。两个数组必须存在但可为空，不规定固定条数。

### JSON Schema（Draft 2020-12）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "APT-Bench Argument-Aware Reverse Task",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "writing_goal",
    "central_question",
    "argumentative_throughline",
    "conceptual_scope",
    "constraints"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "apt_task_v1_1"
    },
    "writing_goal": {
      "type": "string",
      "minLength": 1,
      "pattern": "\\S"
    },
    "central_question": {
      "type": "string",
      "minLength": 1,
      "pattern": "\\S"
    },
    "argumentative_throughline": {
      "type": "string",
      "minLength": 1,
      "pattern": "\\S"
    },
    "conceptual_scope": {
      "type": "array",
      "uniqueItems": true,
      "items": {
        "type": "string",
        "minLength": 1,
        "pattern": "\\S"
      }
    },
    "constraints": {
      "type": "array",
      "uniqueItems": true,
      "items": {
        "type": "string",
        "minLength": 1,
        "pattern": "\\S"
      }
    }
  }
}
```

Schema 仅验证结构和类型。**不能仅因为 JSON 合法就认为任务自足、主线准确或无泄漏。**

### 最终 Task 示例（格式演示，未经单条审核）

```json
{
  "schema_version": "apt_task_v1_1",
  "writing_goal": "Develop an academic assessment of when demographic change raises wider social concerns and what institutional considerations may follow.",
  "central_question": "How might demographic patterns relate to long-term social outcomes, and under what conditions could institutional responses be justified?",
  "argumentative_throughline": "Connect possible mechanisms of demographic change to an assessment of wider implications, and relate that assessment to the grounds and limitations of institutional responses without prescribing a verdict.",
  "conceptual_scope": [
    "demographic patterns",
    "social mechanisms",
    "long-term societal implications",
    "institutional responses"
  ],
  "constraints": []
}
```

该例只说明字段职责，不是可无条件套用的写作模板，更不能作为某一实际 Fragment 已审核的结果。

## 7. Prompt 3：独立审核、冗余检测与修订

审核 GPT 可接收**原文 + 候选 Task**；必须与 Prompt 2 独立执行，不依赖任务构造模型的自评。

### 审核维度（各 1–5 分）

| 指标 | 关注点 |
|---|---|
| `executability` | 不看原文，任务是否自足且可独立理解 |
| `mainline_retention` | 是否准确保留核心问题和抽象论证主线 |
| `abstraction` | 是否既不空泛，也不变成原文详细提纲 |
| `leakage_safety` | 是否泄漏身份、结论、证据组合、反例解法或源文特有推论链 |
| `field_nonredundancy` | `writing_goal` 与 `argumentative_throughline` 是否重复；概念列表是否变成指令列表 |

原则：**一般主题重合不自动构成泄漏**；只有暴露不应预先提供的原文特有答案、独特论证或身份信息时才属于实质风险。泄漏风险不能被其他高分抵消。

建议各维度至少 4/5 且没有明确高风险泄漏才能批准；这属于工程默认门槛，而不是实验验证的最优参数。

### Prompt 3（可复制）

```text
You are an INDEPENDENT reviewer for APT-Bench reverse tasks.

Inputs: one source fragment and one candidate apt_task_v1_1 JSON.
Review the TASK only. Do not write a new academic passage.

Rate each dimension from 1 to 5:
- executability
- mainline_retention
- abstraction
- leakage_safety
- field_nonredundancy

Check:
- Can the task be understood without the source?
- Does argumentative_throughline reflect the core broad dependencies?
- Does it leak a distinctive conclusion, evidence combination,
  counterexample solution or detailed inferential route?
- Does writing_goal repeat the through-line?
- Does conceptual_scope contain concepts rather than imperative actions?
- Are constraints genuinely necessary rather than generic boilerplate?

Do not equate normal topic overlap with leakage.
Material source-specific leakage must trigger revision regardless of
the other scores. Give precise, actionable corrections.

Return only:
{
  "decision": "approve or revise",
  "scores": {
    "executability": 1,
    "mainline_retention": 1,
    "abstraction": 1,
    "leakage_safety": 1,
    "field_nonredundancy": 1
  },
  "reason": "concise source-grounded explanation",
  "revision_request": "specific changes or null if approved"
}
```

### 修订循环

1. 若返回 `revise`，将 Task 和精确修订要求交给修订调用，**优先压缩重复内容和过细主线**。
2. 若审核指出内部 Argument Map 本身错误，退回 Prompt 1 重做，不能只通过换词掩盖错误。
3. 修订后执行**完整复审**，而不是仅检查上次失败的字段。
4. 建议最多两轮自动修订；仍不通过则标记 `needs_human_review`。不得静默批准或伪造结果。
5. 最终通过 Schema 校验和独立审核，才能写入 `tasks.jsonl`。

## 8. 数据落盘与运行复现

建议最小文件结构：

```text
project/
├── prompts/
│   ├── argument_map.md
│   ├── task_construction.md
│   └── task_audit.md
├── schemas/
│   └── apt_task_v1_1.schema.json
├── outputs/
│   ├── tasks.jsonl
│   ├── argument_maps.jsonl
│   ├── audit.jsonl
│   └── failed.jsonl
└── manifest.json
```

- **`tasks.jsonl`**：每行一个**纯 Task JSON**，严格遵循最终 Schema；不添加 `fragment_id`、作者、原文或审核字段。
- **`argument_maps.jsonl`**：内部分析记录，可能含原文独特论据，必须与最终 Task 隔离。
- **`audit.jsonl`**：`fragment_id`、对应任务哈希、评分、审核决定、修订轮次及原因。
- **`failed.jsonl`**：输入不合格、无法解析、审核无法通过等记录。
- **`manifest.json`**：语料哈希、提示词与 Schema 版本、tokenizer、模型、运行配置、时间戳和计数。

通过单独的内部映射文件，把 `fragment_id` 关联到 `tasks.jsonl` 的行号或 Task 哈希。避免因过滤失败项造成行号错位。若项目已有稳定 TaskSpec 或 JSONL 接口，应设计明确迁移层，不要静默覆盖旧字段。

### 推荐伪代码

```python
for fragment in source_fragments:
    if not eligible(fragment):
        record_failure(fragment, "ineligible")
        continue

    arg_map = call_gpt(prompt_1, fragment.text)
    validate_argument_map(arg_map)

    task = call_gpt(prompt_2, arg_map)
    validate_task_schema(task)

    for attempt in range(MAX_REVISIONS + 1):
        review = call_gpt(prompt_3, fragment.text, task)

        if approved(review) and validate_task_schema(task):
            save_task(task)
            save_audit(fragment, review, status="approved")
            break

        if attempt == MAX_REVISIONS:
            save_audit(fragment, review, status="needs_human_review")
            break

        if argument_map_is_wrong(review):
            arg_map = redo_argument_analysis(fragment)

        task = revise_task(task, review, arg_map)
```

实现时必须隔离各调用的上下文，避免 Prompt 2 隐性继承原文全文、作者身份或未经筛选的详细 Argument Map 以外内容；格式错误可单独修复，但不能通过“格式修复”静默改变任务语义。

## 9. 验收标准与失败处理

| 常见失败 | 表现 | 处理 |
|---|---|---|
| 主线缺失 | 只有泛化主题，没有有效论证关系 | 从内部核心依赖重提主线 |
| 主线过细 | 重现原文逐段顺序、证据与结论 | 压缩为宏观关系，去掉答案 |
| 主线错置 | 把历史类比或举例当成中心主张 | 回到 Argument Map 重新分析 |
| 字段重复 | 两个字段写同一串“分析—评价—回应” | 目标归 `writing_goal`，推进归 `argumentative_throughline` |
| 概念过密 | `conceptual_scope` 列出全部细分论点 | 只保留定义任务所需概念 |
| 模板污染 | 每条 Task 都套“原因—影响—对策” | 根据各原文学术论证类型抽象 |
| 来源泄漏 | 包含作者身份、专有例子或独特推论组合 | 删除、泛化并复审 |
| 结构无效 | 缺字段、多字段、错误类型 | JSON Schema 校验；不静默容错 |

**完成标准**：Fragment 资格合格；内部分析可信；最终 `apt_task_v1_1` 结构合法；抽象主线清晰且非提纲；字段不重复；任务自足、结论开放、无明显源文特有内容泄漏；独立审核批准；审计可追踪。

## 10. 最终实施决议

1. 使用 **Argument Map → Answer-neutral Abstraction → Independent Audit** 三阶段流程。
2. Argument Mining 用于**内部结构理解**，同时兼顾篇章功能；不必训练专用模型。
3. 最终 Schema 使用**五个实质字段 + 一个版本字段**，`argumentative_throughline` 为核心。
4. **不恢复 `reasoning_requirements`**；额外加强 `field_nonredundancy` 审核。
5. 只生产 Task 数据，不执行 Task，也不引入额外生成实验。
6. 先遵循现有语料 eligibility、tokenizer、权限与复现要求；对于冲突采取明确版本迁移而非静默覆盖。

本方案是具有相关学术依据的、当前可直接实施的项目方法规范。它不宣称那些论文验证了本项目的具体 Schema，也不宣称当前小样本 Pilot 已经证明全领域有效。
