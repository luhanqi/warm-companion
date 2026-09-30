# 模型清单

| 目录 | 约占空间 | 功能 | 是否直接参与项目 |
| --- | ---: | --- | --- |
| `models/Qwen2.5-1.5B-Instruct/` | 约 3 GB | 自训练对话模型的基础模型 | 是，与 LoRA 适配器组合 |
| `train/outputs/sft-1.5b/adapter/` | 约 81 MB | 暖伴风格与任务能力 LoRA 适配器 | 是，用户自行训练成果 |
| `models/SenseVoiceSmall/` | 约 0.88 GB | 中文语音识别、情感/事件信息 | 是 |
| `models/fsmn-vad/` | 小于 10 MB | 语音活动检测 | 是 |
| `models/bge-m3/` | 约 4.27 GB | 私人记忆语义向量 | 是 |
| `models/bge-reranker-v2-m3/` | 约 2.14 GB | 记忆候选重排 | 是 |
| `models/Qwen2-VL-2B-Instruct/` | 约 4.13 GB | 老照片内容理解 | 是 |
| `models/Fun-CosyVoice3-0.5B-2512/` | 约 9.08 GB | 个性化语音合成 | 是，官方代码和环境位于 `runtime/` |
| `models/Wan2.2-TI2V-5B/` | 约 31.85 GB | 图像/文本到记忆视频 | 权重完整；本机缺少 24 GB NVIDIA 显存，不能推理 |

## 未打包内容

- `runtime/` 已保留本机可直接运行的 Python 环境及 CosyVoice 官方推理代码；换电脑时可按 README 重建。
- `runtime/pip-cache*`、`runtime/conda-pkgs/`、模型下载缓存不是模型成果，提交空间不足时可以删除。
- 旧检查点和重复导出：只保留最终 LoRA adapter。
- API 密钥、真实数据库、用户上传、日志和 PID：涉及隐私或可重建。

模型权重需遵守各自原始许可证；比赛展示或对外发布前应再次核对许可和署名要求。
