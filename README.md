# Argument-Aware Task Generation v1.1

从一篇学术长文本生成一个独立可执行、结论开放的写作 Task。方法规范见
[methodology.md](methodology.md)。规范中的 Fragment 指输入长文本，不能与语料包中
100–300 tokens 的 paragraph 混淆；通常使用清理版 passages.jsonl。

## 流程

分析原文并检查资格 → 内部 Argument Map → 仅凭 Map 构造 Task →
独立读取原文与 Task 审核 → 批准或定向修订。

审核五项分别至少4分，高风险泄漏单独否决。初稿后最多两轮语义修订；Map 错误
会重新分析原文，再构造并完整复审，占用同一修订预算。仍不通过进入人工复核。
非论证型的概念澄清、历史讨论允许没有确定中心主张，关系不足时允许空数组。

最终 Task 恰好包含：schema_version、writing_goal、central_question、
argumentative_throughline、conceptual_scope、constraints。
writing_goal 定义思想工作，central_question 定义开放问题，throughline 描述宏观逻辑
依赖，scope 只列必要概念，constraints 只列特殊边界。没有 reasoning_requirements。
JSON 类型合法不能替代语义审核。

## 使用

仅使用现有 `C:\Users\13811\.conda\envs\MSAP\python.exe -B -X utf8`，无需安装。
以下命令在本项目目录运行。`PY` 表示上述解释器，不是新环境。

```text
PY pipeline.py init --source ../outputs/domain_cleaned_20261101/philosophy/passages.jsonl --run runs/small_trial --limit 1
PY pipeline.py next --run runs/small_trial
```

next 返回单个 job_path。由一个新上下文 agent 完整读取此 JSON，把响应写到包内
output_path，然后由协调者登记：

```text
PY pipeline.py submit --run runs/small_trial --job J000001 --response runs/small_trial/responses/J000001.json --actor fresh_agent_001 --model actual_host_model
PY pipeline.py next --run runs/small_trial
PY pipeline.py export --run runs/small_trial
```

响应格式为 `{job_id, input_hash, result}`，前两项必须原样复制当前 job。
result 的结构在各阶段提示词中给出。每个调用必须使用新 actor；实际隔离由宿主的
fresh-context agent 实现，程序能校验登记和数据包分离，不能证明宿主没有偷读文件。
model 应记录宿主实际提供的模型名；宿主未暴露型号时填写
`native_host_model_unspecified`，不推测或虚构具体型号。
默认最多准备3条，显式 limit 才改变数量；init/next 不自动消费模型额度。
未完成的 job 会原样返回，成功提交不会重复执行。单协调者操作一个 run，勿并发写入。

输入支持 `{fragment_id,source_text}` JSONL 或本项目原有 passage 行。
附带 source_spans 时必须能从同目录或 authors/作者ID下的 source_units.jsonl 精确恢复。
tokenizer 使用本地固定 E5 缓存，记录文件哈希，不下载。沿用原项目1200–3000约定，
不另加1500分界；长度偏离只标注，资格由分析 agent 判断。

## 输出与隔离

- outputs/tasks.jsonl：通过审核的纯六字段 Task，保持原输入顺序。
- private/task_index.jsonl：fragment_id、输出行号、Task/source哈希、批准审核ID。
- private/argument_maps.jsonl：每次分析结果与证据短引语。
- private/audit.jsonl：每轮完整五维审核，关联对应任务哈希、actor与模型。
- private/failed.jsonl：不合格、人工复核、结构或绑定错误。
- private/receipts/：所有被接受的阶段响应，保留修订版本。
- manifest.json、protocol/：冻结语料、规范、提示词、Schema、tokenizer及运行配置。

内部ID及身份只保存在受控索引；构造者只收到 Map，不收到全文、来源信息或分析者
上下文。审核者只收到原文和当前 Task，不收到 Map、修订次数或历史评分。Map 中
证据可能含细节，构造与独立审核必须共同消除泄漏。任务语言默认随原文。

格式错误会记录并拒绝，当前 job 保留，不自动修改任何语义；修正响应后可重新提交。
不得把失败的语义审核伪装成格式修复以反复抽审。运行中不改冻结协议；方法变化新建 run。

v1.1 与旧 task_generation_v1.py 及其产物并存，不把旧七字段结果直接转换成已批准
六字段 Task。历史样本要进入新流程就作为源文重新分析、构造、审核。

## 检验

```text
PY -m unittest discover -s tests -v
```

测试以显式标记的合成响应验证隔离、修订路由、审核门槛、输入绑定及映射，不能冒充
模型实验或证明任务语义质量。本项目只生成 Task，不执行 Task 写正文。

单篇真实试跑说明见 [PILOT.md](PILOT.md)。运行数据保存在本地 runs/ 中，
项目发布包只包含代码、提示词、规范、测试和试跑说明。
