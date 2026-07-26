# 阶段 3：FCFS 对照与单变量调度实验合约

本文冻结 NanoServeLab 阶段 3 第一版调度策略比较的基线身份、单变量边界、实验矩阵、指标报告和证据规则。合约 ID 为 `NSL-S3-SCHED-v1`。

本文只定义后续实现和实验必须遵守的规则，不修改 `Scheduler`、KV Cache、阶段 2 driver、冻结 workload 或既有原始结果，也不产生任何调度性能结论。

## 研究问题与当前切片

阶段 3 要回答：

> 在同一模型、硬件、长短混合 workload 和指标定义下，只改变请求选择策略，长度优先、显式 Priority 与 Aging 是否能改善短请求延迟或整体尾延迟，同时避免不可接受的吞吐和长请求公平性退化？

当前切片先完成三件事：

1. 精确描述现有 Scheduler 中哪些行为构成 FCFS 对照；
2. 冻结后续策略比较时允许改变和禁止改变的变量；
3. 规定原始证据、重复运行、聚合和结论边界。

合约审阅前不实现策略。每一种策略在进入代码前还必须有精确、可测试、带版本号的定义；不能用“智能调度”“优先级更高”等模糊描述代替排序键和并列规则。

## 基线身份：`fcfs-v1`

阶段 3 将当前上游形状的 Scheduler 行为命名为 `fcfs-v1`。这里的 FCFS 指 **waiting 请求的初始准入顺序**，不表示整个引擎严格按到达顺序逐个完成请求。

### Waiting 队列

当前行为由 [`scheduler.py`](../../nanovllm/engine/scheduler.py) 固定：

- `Scheduler.add()` 使用 `waiting.append(seq)`，新请求进入队尾；
- Prefill 每次只从 `waiting[0]` 开始判断，不能因为后续请求更短或更容易分配而绕过队首；
- 队首 KV Block 无法准入时直接停止本轮 Prefill，形成显式 Head-of-Line blocking；
- 队首请求允许使用 Chunked Prefill；Prompt 尚未完成时仍停留在 waiting 队首；
- 只有 Prompt 本轮全部完成时，请求才从 waiting 队首移除并追加到 running 队尾；
- 预算允许时，同一纯 Prefill 批次可以继续按 waiting 顺序准入后续请求；
- 只要本轮成功调度至少一个 Prefill，请求批次就立即返回，不在同一 step 混入 Decode。

因此，`fcfs-v1` 同时包含“waiting 队首准入”和“Prefill 相对 Decode 的 step 级优先”，后者必须作为固定引擎不变量保留，不能在长度优先切片中顺便改变。

### Running 队列

当前 Decode 不是“先到请求一直跑到结束”，而是按 running 队列轮转：

- 每轮从 running 队首依次取请求；
- 每个成功准入的 running 请求本轮只调度 1 个 Token；
- 本轮选择完成后，Scheduler 恢复这些请求的原有相对顺序；
- 已完成请求在 `postprocess()` 中从 running 移除并释放 KV Block。

所以 `fcfs-v1` 的准确表述是：

> waiting 阶段 FCFS 队首准入，running 阶段保持稳定顺序的一 Token 轮转。

不得把它描述成串行完成式 FCFS，也不得仅凭请求完成顺序推断 waiting 选择顺序。

### 抢占与恢复

Decode 追加 KV Block 失败时：

- 优先抢占当前 running 队尾请求；
- 被抢占请求释放全部 KV Block，状态回到 `WAITING`；
- 被抢占请求通过 `waiting.appendleft(seq)` 回到 waiting 队首；
- 如果没有其他 running 请求可牺牲，则当前请求自身被抢占；
- 重新调度时需要再次 Prefill，Initial Queue Time 不会重置，但额外等待会自然进入 TTFT、TPOT 或 E2E。

抢占恢复的“回队首”优先于普通到达顺序，是 `fcfs-v1` 的一个例外规则。阶段 3 第一种长度策略不得同时修改抢占受害者选择、KV 释放或回队位置。

### Prefix Cache 与资源预算

以下机制会影响实际工作量，但不属于阶段 3 第一轮的策略自变量：

- Prefix Cache 匹配和命中；
- `max_num_seqs`；
- `max_num_batched_tokens`；
- KV Block 大小、数量和分配失败；
- Chunked Prefill；
- 每个 step 只允许纯 Prefill 或纯 Decode。

这些机制在 FCFS 与候选策略之间必须保持一致。阶段 3 不关闭 Prefix Cache，也不把 Cache 命中收益冒充调度收益。

## 单变量比较矩阵

策略按下列顺序研究，不并行叠加：

| 顺序 | Policy ID | 唯一允许改变的选择因素 | 固定的并列规则 | 当前状态 |
| ---: | --- | --- | --- | --- |
| 0 | `fcfs-v1` | 无；保持现有 Scheduler 行为 | 到达顺序 | 已有行为，需补多请求顺序测试 |
| 1 | `prompt-length-v1` | 新到达请求在 waiting 中按 `num_prompt_tokens` 升序插入 | 相同长度保持到达顺序 | 第一实现候选 |
| 2 | `explicit-priority-v1` | 使用版本化、显式提供的整数 Priority | Priority 相同保持到达顺序 | 后续单独冻结 Priority overlay |
| 3 | `aging-v1` | 在已冻结的 Priority 基础上只增加等待时间修正 | 分数相同保持到达顺序 | 后续单独冻结 Aging 公式 |

### `prompt-length-v1` 的第一版定义

第一种候选策略只允许改变 **新请求进入 waiting 时的位置**：

- 排序键为请求准入时已经确定的 `Sequence.num_prompt_tokens`；
- Token 数较少的请求排在较前；
- 相同 Prompt Token 数严格保持到达顺序；
- 不使用 `max_tokens`、已生成 Token、Prefix Cache 命中、request class 或运行时预测；
- waiting 队首已经开始 Chunked Prefill（存在 `block_table`）或已经生成 Completion Token 的恢复请求，组成不可被新到达请求越过的 recovery prefix；
- 只在 recovery prefix 之后的尚未开始请求中按长度稳定插入；
- 被抢占请求仍按现有行为回到 waiting 队首；
- running Decode 顺序、Prefill 优先、KV 分配和完成规则全部不变。

选择“recovery prefix 之后准入时稳定插入”而不是“每次 schedule 全队重排”，是为了让第一切片只改变尚未开始请求的 waiting 顺序，不同时改变 Chunked Prefill 恢复和抢占语义。当前 saturated workload 的 64 个 measured 请求全部在第一次 `step()` 前准入，因此正式对照中的初始队列会按 Prompt 长度稳定排列；上述 recovery 规则同时约束未来在线到达语义。

### 后续 Priority 与 Aging 的门槛

`explicit-priority-v1` 实现前必须新增一个独立、带哈希的 Priority overlay，并让 FCFS 对照也接收同一份 metadata 但忽略它。不得直接把 `short` 类硬编码成高优先级，否则无法区分“长度策略”和“显式业务 Priority”。

`aging-v1` 实现前必须固定：

- 使用单调时间还是 Scheduler step 数；
- 等待起点和抢占后重新等待的计算方式；
- 具体公式、阈值、单位、上限；
- 与 base Priority 的组合方式；
- 并列规则和数值稳定性。

在这些参数被版本化并由项目所有者审阅前，不编写 Aging 代码，也不调参寻找最好结果。

## 固定实验输入

阶段 3 继续复用已冻结的 `NSL-S2-SAT-v1` 请求 manifest，不创建内容不同但沿用旧 ID 的 workload。

| 项目 | 固定值 |
| --- | --- |
| Workload | `NSL-S2-SAT-v1` |
| Manifest SHA-256 | `aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d` |
| 到达模型 | 64 个请求全部在第一次 measured `step()` 前准入 |
| 请求顺序 | `[short, long, short, short] * 16` |
| Short | 48 个；128 Prompt / 32 Output Token |
| Long | 16 个；1024 Prompt / 256 Output Token |
| Workload seed | 0 |
| Sampling seed | 0 |
| 模型 | `Qwen/Qwen3-0.6B` |
| Model revision | `c1899de289a04d12100db370d81485cdf75e47ca` |
| Sampling | temperature 0.6；`ignore_eos=True` |
| Engine | eager false；model len 4096；max seqs 512；max batched tokens 16384；GPU memory 0.9；TP 1；KV block 256 |
| 正式硬件 | 同一台 Windows WSL2 + RTX 4060 Laptop GPU |

模型、依赖、驱动、硬件、manifest、seed、warmup、测量边界和聚合公式中任一项变化，都不能继续归入同一个策略比较组。

## 阶段 2 FCFS 结果的使用边界

阶段 2 的 `851.900666 ± 22.081773 output Token/s` 是 `NSL-S2-SAT-v1` 的历史 FCFS 锚点，用于：

- 检查阶段 3 新 FCFS 是否出现无法解释的数量级漂移；
- 保留研究进展的连续性；
- 帮助发现环境、driver 或默认行为意外变化。

它不能直接作为阶段 3 新策略的唯一因果对照。原因包括：

- 阶段 3 需要显式记录 Policy ID；
- 后续可能增加策略选择入口和 stage 3 raw schema；
- 不同日期的 GPU 热状态与后台负载没有完全受控；
- 候选策略必须与同一阶段 3 源码和运行协议下的 FCFS 比较。

因此，每个候选策略的正式对照都必须包含新的 `fcfs-v1` 三次独立进程运行。阶段 2 raw 不删除、不回填，也不重标为阶段 3 raw。

## 正式运行设计

### 同一源码与显式策略身份

一次正式策略对照组应使用同一个 clean commit 构建 FCFS 和候选策略，通过显式 Policy ID 选择行为。默认值必须是 `fcfs-v1`，且默认路径需要行为等价测试。

阶段 3 raw 至少要新增并固定：

```text
experiment_contract = NSL-S3-SCHED-v1
policy.id
policy.definition_version
policy.parameters
workload.id
workload.manifest_sha256
repository.commit
repository.dirty
```

现有阶段 2 schema/aggregator 不认识 Policy ID，并把 `NSL-S2-SAT-v1` 固定为唯一实验身份。阶段 3 必须使用新的实验/schema 身份和兼容性校验，不能静默修改旧 raw，也不能让旧 aggregator 把不同策略混成同一组。

### 重复次数与顺序

每个 `fcfs-v1` 与候选策略对照组：

- FCFS：3 个全新 Python/LLM 进程；
- 候选策略：3 个全新 Python/LLM 进程；
- 六次运行都执行相同 warmup、CUDA 同步和 saturated admission；
- 预先固定运行顺序为 `FCFS-1 → Candidate-1 → Candidate-2 → FCFS-2 → FCFS-3 → Candidate-3`；
- 不因某次结果较差而删除、替换或悄悄重跑；
- 运行失败时保留失败 artifact 和日志；若修复后重做，使用新的 experiment group ID，原失败组继续保留。

该交错顺序让两种策略都经历一次相邻重复，并避免所有 FCFS 完全早于所有 Candidate。它不能消除温度、功耗和时钟变化，因此运行顺序和缺少连续硬件遥测仍必须写入限制。

### 正式运行前门槛

每个对照组开始前必须验证：

- 精确 commit，tracked worktree clean；
- Policy ID 与参数能从 raw 唯一恢复；
- `NSL-S2-SAT-v1` manifest 指纹一致；
- GPU 可见且无其他 compute process；
- 模型 revision 和权重证据一致；
- 全部 Mac CPU 测试通过；
- WSL2 全部测试及每个 Policy 的一次真实 CUDA smoke 通过；
- FCFS 默认路径与合约不变量测试通过；
- 输出目录此前不存在或为空，writer 默认拒绝覆盖。

## 指标与公平性报告

继续使用 [`metrics.md`](metrics.md) 已固定的事件和公式，不重新定义 TTFT、TPOT、E2E 或 Initial Queue Time。

每个 Policy 必须报告：

- finished、failed、cancelled、incomplete、invalid 和 unmapped 数量；
- 每次运行的 Request/s、Output Token/s；
- 跨 3 次运行的 mean、sample SD、median、min、max、P50、P95、P99；
- all、short、long 三组的 Queue Time、TTFT、Mean TPOT、E2E；
- 每组指标的 `n`、mean、sample SD、median、min、max、P50、P95、P99；
- 相对同组 FCFS 的绝对差值和百分比差值；
- 最大 Queue Time、最大 TTFT 和最大 E2E 对应的 request class 与 request index。

### 第一版公平性解释

第一版不引入 Jain Index 或单一“公平性分数”。公平性使用可以追溯到请求类别和原始时间戳的直接证据：

- short 与 long 分组分别报告；
- long 的 P95/P99/max TTFT 与 E2E 不得隐藏；
- 报告 short/long 的 mean、P95、P99 和 max 差值；
- 报告所有未完成或无效请求；
- Initial Queue Time 只表示第一次调度前等待，不能冒充抢占后的累计等待；
- 若发生抢占，额外等待需要结合 TTFT、TPOT、E2E 和 Scheduler 行为解释。

任何“改善短请求”的表述都必须紧邻 long 请求、吞吐和完成率变化。不能只选择一个更好看的 percentile 宣布策略获胜。

### 描述性警戒线

第一版设置两个预先声明的解释警戒线，而不是统计显著性检验：

- 候选策略 Output Token/s 的三次运行均值比同组 FCFS 低超过 5%，标记为“吞吐退化需解释”；
- 任一请求类别出现未完成，或其 P95/P99/max TTFT/E2E 明显上升，标记为“公平性风险”，逐项报告而不是用整体均值掩盖。

`n=3` 不足以仅凭常规显著性措辞证明稳定总体提升。警戒线只帮助一致解释，不是删除负面结果或自动判定策略无效的理由。

## 百分比方向与结论规则

统一使用：

```text
relative_delta_percent = (candidate - fcfs) / fcfs * 100
```

- 对吞吐：正值通常更好；
- 对延迟：负值通常更好；
- 表格必须明确方向，不能把负延迟差写成“负优化”造成歧义。

候选策略可以得到以下结论之一：

- 在当前固定实验中观察到重复方向一致的改善；
- 改善伴随吞吐或某类请求公平性退化；
- 三次运行方向不一致，证据不足；
- 没有观察到改善；
- 发生退化；
- 实验或 artifact 无效，不能比较。

禁止写：

- “一定更快”；
- “对所有 workload 有效”；
- “零开销”；
- “统计显著”，除非未来另行固定并满足统计设计；
- 把一次最好运行与 FCFS 平均值比较；
- 把阶段 1、阶段 2 和阶段 3 不同实验身份的吞吐直接混为一组。

## 实现前测试门槛

第一种策略代码开始前，先用确定性 CPU 测试补齐 `fcfs-v1` 多请求不变量：

1. 新请求按到达顺序进入 waiting；
2. Prefill 严格从 waiting 队首准入；
3. 队首资源不足时不绕过后续请求；
4. Chunked Prefill 未完成请求保持队首；
5. Prompt 完成后按顺序进入 running；
6. running 每轮一 Token，轮转后相对顺序不变；
7. Prefill 成功时同一 step 不混入 Decode；
8. KV 不足时抢占 running 队尾并回 waiting 队首；
9. 默认 Policy 为 `fcfs-v1`，与改动前顺序快照等价；
10. `prompt-length-v1` 只改变 recovery prefix 之后的新到达 waiting 插入位置，相同长度稳定；
11. 长度策略不改变 Decode、抢占、KV、Prefix Cache 或完成语义。

测试使用小型 fake config 和确定性 Token，不使用 `sleep`，不依赖 CUDA。CPU 测试证明选择语义，不证明 GPU 性能。

## 分阶段交付顺序

阶段 3 后续工作按以下小切片串行推进：

1. 合并本合约；
2. 新增 FCFS 多请求顺序测试，不改变运行行为；
3. 增加显式 Policy 选择入口，默认 `fcfs-v1`，完成行为等价测试；
4. 实现 `prompt-length-v1` 的稳定 waiting 插入与 CPU 测试；
5. 建立 stage 3 raw/schema/driver Policy 身份和拒绝混组校验；
6. 在 WSL2 对 FCFS 与长度策略分别完成 smoke；
7. 按固定六次顺序运行正式对照，保存 raw、日志和哈希；
8. 离线聚合、独立复算并如实记录正面、负面或不确定结果；
9. 只有长度策略完成收口后，才冻结 `explicit-priority-v1`；
10. Priority 收口后再冻结 `aging-v1`。

每个切片都使用独立分支、小提交和测试。不得在同一 PR 同时实现多种策略或边跑结果边调整排序参数。

## 当前明确不做

- 不修改 KV Cache、BlockManager 或 Prefix Cache；
- 不改变 Decode batching 或每轮 Token 数；
- 不改变 Prefill/Decode 混批规则；
- 不新增在线 Poisson/固定速率到达；
- 不实现 Prefix Cache 感知评分；
- 不做 Scheduler trace/JSONL 扩展；
- 不制作最终图表或论文结论；
- 不用阶段 2 raw 伪装阶段 3 新对照。

## 所有者决策

2026-07-26，项目所有者授权按本合约采用以下默认方向：

- 第一候选策略为按 Prompt Token 数长度优先；
- 相同长度保持到达顺序；
- 公平性先使用长短分组、尾延迟、最坏等待和完成率，不引入复杂综合分数；
- 阶段 2 FCFS 只作历史锚点，阶段 3 使用新 FCFS 与候选策略公平对照；
- 合约完成并审阅后，再开始最小 Scheduler 行为修改。

这些是研究设计选择，不是上游默认值，也不是实验得出的最优设置。后续如要改变，必须更新合约版本和实验身份，不覆盖既有 raw 或结果记录。
