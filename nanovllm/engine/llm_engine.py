"""LLM 推理引擎的总编排入口。

核心职责：
- 接收文本或 Token 请求，构造 ``Sequence`` 并交给 ``Scheduler``。
- 初始化 tokenizer、张量并行进程、主 rank 的 ``ModelRunner`` 和 Scheduler。
- 在 ``step()`` 中串起“调度 -> GPU 执行 -> 状态提交”的完整请求生命周期。
- 在 ``generate()`` 中循环 step，直到所有请求完成并解码输出。

重要成员：
- ``model_runner``：执行模型前向、KV Cache 写入和采样。
- ``scheduler``：选择本轮请求并维护 waiting/running 状态。
- ``ps`` / ``events``：张量并行从属进程及其同步事件。
- ``diagnostic_trace_recorder``：默认关闭的逐 step 只读观察器。

阅读顺序：``add_request()`` -> ``step()`` -> ``generate()``。注意 ModelRunner
会先根据 GPU 显存写回 ``config.num_kvcache_blocks``，随后 Scheduler 才能创建
与物理 KV Cache 容量一致的 BlockManager。
"""

import atexit
from dataclasses import fields
from time import perf_counter
from tqdm.auto import tqdm
from transformers import AutoTokenizer
import torch.multiprocessing as mp

from nanovllm.config import Config
from nanovllm.sampling_params import SamplingParams
from nanovllm.engine.sequence import Sequence
from nanovllm.engine.scheduler import Scheduler
from nanovllm.engine.model_runner import ModelRunner
from nanovllm.engine.request_timing import RequestTimingRecorder
from nanovllm.engine.diagnostic_trace import DiagnosticTraceRecorder


class LLMEngine:

    def __init__(
        self,
        model,
        *,
        timing_recorder: RequestTimingRecorder | None = None,
        diagnostic_trace_recorder: DiagnosticTraceRecorder | None = None,
        **kwargs,
    ):
        config_fields = {field.name for field in fields(Config)}
        config_kwargs = {k: v for k, v in kwargs.items() if k in config_fields}
        config = Config(model, **config_kwargs)
        Sequence.block_size = config.kvcache_block_size
        self.ps = []
        self.events = []
        ctx = mp.get_context("spawn")
        for i in range(1, config.tensor_parallel_size):
            event = ctx.Event()
            process = ctx.Process(target=ModelRunner, args=(config, i, event))
            process.start()
            self.ps.append(process)
            self.events.append(event)
        self.model_runner = ModelRunner(
            config,
            0,
            self.events,
            diagnostic_trace_recorder=diagnostic_trace_recorder,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(config.model, use_fast=True)
        config.eos = self.tokenizer.eos_token_id
        self.scheduler = Scheduler(
            config,
            timing_recorder=timing_recorder,
            diagnostic_trace_recorder=diagnostic_trace_recorder,
        )
        self.diagnostic_trace_recorder = diagnostic_trace_recorder
        atexit.register(self.exit)

    def exit(self):
        self.model_runner.call("exit")
        del self.model_runner
        for p in self.ps:
            p.join()

    def add_request(self, prompt: str | list[int], sampling_params: SamplingParams):
        if isinstance(prompt, str):
            prompt = self.tokenizer.encode(prompt)
        seq = Sequence(prompt, sampling_params)
        self.scheduler.add(seq)

    def step(self):
        recorder = self.diagnostic_trace_recorder
        if recorder is not None:
            recorder.begin_step(self.scheduler)
        seqs, is_prefill = self.scheduler.schedule()
        if recorder is not None:
            recorder.after_schedule(self.scheduler, seqs, is_prefill)
        num_tokens = sum(seq.num_scheduled_tokens for seq in seqs) if is_prefill else -len(seqs)
        token_ids = self.model_runner.call("run", seqs, is_prefill)
        if recorder is not None:
            recorder.after_runner()
        self.scheduler.postprocess(seqs, token_ids, is_prefill)
        if recorder is not None:
            recorder.finish_step(self.scheduler)
        outputs = [(seq.seq_id, seq.completion_token_ids) for seq in seqs if seq.is_finished]
        return outputs, num_tokens

    def is_finished(self):
        return self.scheduler.is_finished()

    def generate(
        self,
        prompts: list[str] | list[list[int]],
        sampling_params: SamplingParams | list[SamplingParams],
        use_tqdm: bool = True,
    ) -> list[str]:
        pbar = tqdm(total=len(prompts), desc="Generating", dynamic_ncols=True, disable=not use_tqdm)
        if not isinstance(sampling_params, list):
            sampling_params = [sampling_params] * len(prompts)
        for prompt, sp in zip(prompts, sampling_params):
            self.add_request(prompt, sp)
        outputs = {}
        prefill_throughput = decode_throughput = 0.
        while not self.is_finished():
            t = perf_counter()
            output, num_tokens = self.step()
            if num_tokens > 0:
                prefill_throughput = num_tokens / (perf_counter() - t)
            else:
                decode_throughput = -num_tokens / (perf_counter() - t)
            pbar.set_postfix({
                "Prefill": f"{int(prefill_throughput)}tok/s",
                "Decode": f"{int(decode_throughput)}tok/s",
            })
            for seq_id, token_ids in output:
                outputs[seq_id] = token_ids
                pbar.update(1)
        pbar.close()
        outputs = [outputs[seq_id] for seq_id in sorted(outputs.keys())]
        outputs = [{"text": self.tokenizer.decode(token_ids), "token_ids": token_ids} for token_ids in outputs]
        return outputs
