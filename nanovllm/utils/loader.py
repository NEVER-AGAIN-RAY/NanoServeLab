"""将 Hugging Face Safetensors 权重装载到 nano-vLLM 模型结构。

``load_model()`` 遍历模型目录中的 ``*.safetensors``，按参数名查找目标
Parameter，并调用参数自带的 ``weight_loader``；没有专用加载器时直接复制。

``packed_modules_mapping`` 用于处理推理模型中的融合参数，例如把独立的
q/k/v 权重装入一个 QKVParallelLinear，或把 gate/up 权重装入融合 MLP。
该文件只负责权重名称和分片映射，不参与请求调度或运行时 KV Cache 管理。
"""

import os
from glob import glob
import torch
from torch import nn
from safetensors import safe_open


def default_weight_loader(param: nn.Parameter, loaded_weight: torch.Tensor):
    param.data.copy_(loaded_weight)


def load_model(model: nn.Module, path: str):
    packed_modules_mapping = getattr(model, "packed_modules_mapping", {})
    for file in glob(os.path.join(path, "*.safetensors")):
        with safe_open(file, "pt", "cpu") as f:
            for weight_name in f.keys():
                for k in packed_modules_mapping:
                    if k in weight_name:
                        v, shard_id = packed_modules_mapping[k]
                        param_name = weight_name.replace(k, v)
                        param = model.get_parameter(param_name)
                        weight_loader = getattr(param, "weight_loader")
                        weight_loader(param, f.get_tensor(weight_name), shard_id)
                        break
                else:
                    param = model.get_parameter(weight_name)
                    weight_loader = getattr(param, "weight_loader", default_weight_loader)
                    weight_loader(param, f.get_tensor(weight_name))
