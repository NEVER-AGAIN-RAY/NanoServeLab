# 阶段 2：离线 schema v1 Aggregation 合约

本文冻结 NanoServeLab 阶段 2 的离线汇总器输入兼容键、record 分类、统计规则与 aggregate schema v1。实现位于 `research/stage2_aggregate.py`。它只读取已写出的 schema v1 raw JSON，不修改 Scheduler、timing recorder、saturated driver、`bench.py` 或冻结 workload。

实时进度仍以 [`docs/project/README.md`](../project/README.md) 为准。指标公式与 nearest-rank / sample SD 规则继承 [`metrics.md`](metrics.md)；per-request 重算必须复用 `derive_request_metrics()`，不得复制 Queue Time / TTFT / E2E / Mean TPOT 公式。

## 目标与限制

本切片回答：在一组兼容的正式 raw 上，如何确定性重算延迟与吞吐统计，并把 outcome / invalid 计数完整保留。

它不是：

- 在线监控或 Dashboard；
- 对 raw 的就地改写、覆盖或派生字段回填；
- 自动扫描目录并混入 smoke / 其他实验文件；
- 性能提升结论或对照组比较。

CLI 必须显式列出每个 raw JSON 路径。本合约不授权把 smoke 或其它 workload ID 混入同一聚合组。

## 输入验证

每个输入文件必须：

1. 可解析为 UTF-8 JSON 对象；
2. `schema_version == 1`；
3. `experiment == "NSL-S2-SAT-v1"`；
4. `repository.dirty == false`；
5. `status` 必须显式为 `"finished"` 或 `"failed"`；
6. 包含可读取的 `run_id`、`run_number`、`requests`、`measurement`、`unmapped_timing_records`、`workload`、`model`、`engine`、`environment`、`repository`。

JSON 中的整数事实必须是真正的 JSON integer；布尔、字符串和小数不做 `int()` 强制转换。`NaN` / `Infinity` 等非有限数一律拒绝。`environment.packages` 等约定为 object / list 的容器不得用其它类型冒充。

此外，单个输入也必须匹配冻结的 workload 身份，而不只是与同组其它文件彼此一致：

- `arrival_model == "saturated_batch"`；
- `seed == 0`；
- `sampling_seed == 0`；
- `request_count == 64`；
- `manifest_sha256 == "aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d"`。

整组拒绝条件（拒绝整个输入，不产出部分聚合）：

- 任一文件 malformed JSON、错误 schema、错误 experiment，或结构损坏到无法读取必需字段；
- 重复 `run_id`、重复 `run_number`，或重复源文件（按解析后的绝对路径去重检测；输出只记录 basename）；
- 任一文件 `repository.dirty` 不为 `false`；
- 兼容键不一致（见下节）。

单条 request 的 outcome / 时间戳无效不得导致整组拒绝：保留计数、标为 `invalid`，并从成功延迟集合排除，不能静默删除。

## 兼容键（必须一致）

同一聚合组内，以下字段必须深度相等。任一差异视为混组并拒绝：

| 区域 | 兼容键 |
| --- | --- |
| repository | `commit` |
| environment | `python`；`packages.torch` / `packages.triton` / `packages.transformers` / `packages.flash-attn` / `packages.xxhash`；`torch_cuda_build`；`cuda_available`；`cuda_device` |
| model | `id`；`revision` |
| engine | 全部固定项（整个 `engine` 对象） |
| workload | `arrival_model`；`seed`；`sampling_seed`；`request_count`；`manifest_sha256` |

明确**不是**兼容键，不得因它们不同而拒绝：

- `repository.branch`
- `created_at_utc`、`run_id`、`run_number`
- `measurement.started_ns` / `ended_ns` 等运行身份或窗口时间戳
- `model.local_path`（机器路径）
- `environment.platform`（本切片不作为实验身份兼容键）

## Record 分类

对每个 raw 的 `requests[]`：

1. 按原始 `outcome` 计入 raw outcome counts：
   - `finished` / `failed` / `cancelled` / `incomplete`；
   - 其它字符串或缺失计入 `other`。
2. 仅当 `outcome == "finished"` 时，构造 `RequestTimingRecord` 并调用 `derive_request_metrics()`：
   - `request_class` 必须为 `short` / `long`；
   - `request_index`、`seq_id`、Token 数和纳秒时间戳必须为严格整数（不接受 bool / string / float）；
   - 同一个 run 的 valid finished records 不得重复 `request_index` 或 `seq_id`，重复项记为 invalid，防止重复计入；
   - `prompt_tokens > 0`、`requested_output_tokens > 0`，且实际 `output_tokens == requested_output_tokens`；
   - 成功 → `valid_finished`，进入延迟集合；
   - 抛 `ValueError` 或无法构造合法 record → `invalid_records`，不进入延迟集合。
3. `failed` / `cancelled` / `incomplete` / `other` 不进入延迟集合；它们不是 `invalid`，除非结构上无法读取 outcome（计入 `other` / 必要时 `invalid` 的边界由实现测试固定）。
4. 顶层 `unmapped_timing_records` 只计数，不派生延迟。

`total_requests` 是所有输入 raw 的 `requests` 条数之和。

## 延迟统计

对 `valid_finished` 请求，使用 `derive_request_metrics()` 得到：

- `queue_time_ms`
- `ttft_ms`
- `e2e_ms`
- `mean_tpot_ms`（单 Token 时为 `null`）

分组：

- `all`：全部 valid finished；
- `short`：`request_class == "short"`；
- `long`：`request_class == "long"`。

每个非空指标集合输出：

- `n`
- `mean`
- `median`
- `min`
- `max`
- `sample_std`：`n >= 2` 时为样本标准差（分母 `n-1`），否则 `null`
- `p50` / `p95` / `p99`：nearest-rank，排序后取第 `ceil(p × n)` 个值（1-based）

Mean TPOT 为 `null` 的请求不进入 TPOT 数值集合；该指标的 `n` 只统计非空 TPOT。其它指标的 `n` 仍包含这些请求。

空集合输出 `n=0`，其余统计字段为 `null`。

## 吞吐统计

每个 run 的吞吐**只能**使用该 run 自己的：

- `measurement.started_ns`
- `measurement.ended_ns`

公式：

```text
window_seconds = (ended_ns - started_ns) / 1e9
request_throughput = valid_finished_count / window_seconds
output_token_throughput = sum(valid_finished.output_tokens) / window_seconds
```

约束：

- 不得跨进程拼接 monotonic clock；
- `started_ns` / `ended_ns` 缺失、不是严格整数，或 `window_seconds <= 0` 时，该 run 的吞吐为 `null`，但 run 仍保留在输出中；
- 顶层 `status == "failed"` 时，即使残留了正数结束边界，窗口与两种吞吐也必须为 `null`；
- failed run 或无效窗口不得伪造结束边界。

跨 run 吞吐：把每个 run 的 `request_throughput` / `output_token_throughput` 当作独立样本，再套用与延迟相同的汇总统计；`null` 样本不进入数值集合，但 run 计数保留。

## Aggregate schema v1

输出写入新文件；使用独占创建，目标文件、符号链接或并发竞争已存在时均拒绝覆盖。输出 JSON 必须确定性写出：稳定键序、UTF-8、结尾换行，且不允许非有限数。每个源文件只读取一次，解析内容与记录的 SHA-256 来自同一份 bytes；源文件身份只记录 basename、SHA-256、`run_id`、`run_number`，不记录依赖机器的绝对路径。

```json
{
  "schema_version": 1,
  "aggregator": "NSL-S2-AGG-v1",
  "experiment": "NSL-S2-SAT-v1",
  "created_at_utc": "...",
  "sources": [
    {
      "basename": "saturated-....-run1.json",
      "sha256": "...",
      "run_id": "...",
      "run_number": 1
    }
  ],
  "compatibility": {
    "repository_commit": "...",
    "environment": {},
    "model": {"id": "...", "revision": "..."},
    "engine": {},
    "workload": {}
  },
  "counts": {
    "total_requests": 0,
    "outcomes": {
      "finished": 0,
      "failed": 0,
      "cancelled": 0,
      "incomplete": 0,
      "other": 0
    },
    "valid_finished": 0,
    "invalid_records": 0,
    "unmapped_timing_records": 0
  },
  "latency_ms": {
    "all": {},
    "short": {},
    "long": {}
  },
  "throughput": {
    "per_run": [
      {
        "run_number": 1,
        "run_id": "...",
        "status": "finished",
        "valid_finished": 0,
        "valid_finished_output_tokens": 0,
        "window_seconds": null,
        "request_throughput": null,
        "output_token_throughput": null
      }
    ],
    "across_runs": {
      "request_throughput": {},
      "output_token_throughput": {}
    }
  }
}
```

`latency_ms.<group>` 内每个指标键为 `queue_time_ms` / `ttft_ms` / `e2e_ms` / `mean_tpot_ms`，值为上述统计对象。

## 验证门槛

- Mac 轻量 package bootstrap 下确定性 CPU fixture 覆盖兼容三 run、分组、统计、小样本 percentile、SD null、TPOT null、outcome/invalid、malformed/混组/重复源与重复 request 身份、冻结 workload 身份、严格整数、failed run 吞吐隔离、非法编码/非有限数、raw 只读、独占输出、import/`--help` 不加载 torch。
- 不读取真实 CUDA，不运行模型。
- 在聚合实现与测试审查通过前，不在正式三份 raw 上发布延迟/吞吐数字，不声称性能提升。
