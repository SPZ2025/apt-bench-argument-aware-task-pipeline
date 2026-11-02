# 单篇真实试跑（2026-11-01）

## 范围与结果

使用清理版哲学语料中的第一条 Russell 篇幅，主题为外观与实在。
输入来自 `outputs/domain_cleaned_20261101/philosophy/passages.jsonl`，
原始候选 CP00001，本次内部标识 F000001；既有 E5 tokenizer 计数为2223 tokens。
已核对正文与所附原文位置可以精确对应。没有生成新正文，没有扩大到批量处理。

三个不同的新上下文原生 agent 分别完成分析、构造、独立审核。
构造者只收到 Argument Map；审核者只收到原文和候选 Task。
宿主未暴露具体模型型号，真实执行记录标为 `native_host_model_unspecified`，
不把这一试跑宣称为某一特定型号的实验。

初稿经独立审核批准，语义修订次数为0。

| 维度 | 得分（1–5） |
|---|---:|
| executability | 5 |
| mainline_retention | 4 |
| abstraction | 5 |
| leakage_safety | 5 |
| field_nonredundancy | 4 |

高风险泄漏：false。审核指出原文末尾关于物理对象是否存在及其性质的问题，
在 Task 中保留得比较概括；主线保留和字段非冗余均为4分，不表示完美。
上述是一次模型审核结果，不是人工质量结论，也不能外推为全领域有效率。

## 实际产出的 Task

```json
{
  "schema_version": "apt_task_v1_1",
  "writing_goal": "Develop a philosophical assessment of the extent to which sensory experience can justify knowledge of physical objects.",
  "central_question": "When appearances depend on perceptual conditions, what, if anything, can sensory experience establish with certainty about physical objects and their relation to what is experienced?",
  "argumentative_throughline": "Relate an account of sensory awareness and its objects to the standards for certain knowledge, assess the epistemic significance of condition-dependent appearances, and connect that assessment to the grounds and limits of claims about material reality.",
  "conceptual_scope": [
    "appearance and reality",
    "sense-data and sensory awareness",
    "perceptual conditions",
    "physical objects and matter",
    "certainty and justification"
  ],
  "constraints": []
}
```

## 发现并修正的格式问题

分析阶段最初响应中的 discourse_functions 使用了对象数组，而校验要求字符串数组；
关系标签还使用了 supports / explains，而固定标签是 support / explanation。
两次不合格式的提交均被拒绝，没有推进流程。

本次格式修复将每个篇章功能对象完整序列化为字符串，保留其所有键值，
并仅规范上述两个关系标签的拼写，没有添加、删除或重新判断语义。
修复前响应、被拒绝的响应和修复说明均保存在本地试跑目录中。
后续运行使用的分析提示词已明确这些类型与枚举要求。
本次运行继续保留原冻结提示词，没有篡改已经执行的协议快照。

## 程序检验与本地记录

16项程序测试通过，覆盖字段约束、上下文数据包分离、证据定位、五项门槛、
泄漏否决、Map重做、最多两轮修订、完整复审、恢复运行、响应绑定和结果映射。
这些测试使用明确标记的合成响应，只检验程序行为，不计入真实模型实验。

完整试跑位于 `runs/pilot_20261101/`：

- `outputs/tasks.jsonl`：获批的纯六字段 Task。
- `private/task_index.jsonl`：Task与源文的独立对应关系。
- `private/argument_maps.jsonl`、`private/audit.jsonl`：内部分析与审核记录。
- `private/receipts/`：各阶段真实响应及执行登记。
- `responses/format_repair_note.json`：格式修复说明。
- `manifest.json`、`protocol/`：本次使用的冻结输入信息及运行协议。

项目ZIP不包含原文、上述内部运行目录或大批量语料；本说明保留一条实际Task作为示例。
