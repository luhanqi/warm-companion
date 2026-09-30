# 暖伴 1.5B LoRA 适配器

- 基础模型：`Qwen/Qwen2.5-1.5B-Instruct`
- 本地基础模型：`models/Qwen2.5-1.5B-Instruct/`
- 适配器权重：`adapter_model.safetensors`
- 训练轮数：3

运行时由 `train/serve.py` 加载基础模型，再叠加本目录的 PEFT/LoRA 权重。适配器不能脱离基础模型单独推理，也不能接到 0.5B 模型上。
