# 本地模型目录

本目录在完整比赛交付包中保存约 55 GB 的本地模型权重。GitHub 对普通文件和 Git LFS 都有单文件及配额限制，因此权重文件不直接提交到代码仓库；这里只保留模型清单与恢复说明。

完整离线包应包含以下目录：

- `Qwen2.5-1.5B-Instruct/`：暖伴对话基础模型
- `SenseVoiceSmall/`：语音识别
- `fsmn-vad/`：语音活动检测
- `bge-m3/`：私人记忆向量
- `bge-reranker-v2-m3/`：记忆重排
- `Qwen2-VL-2B-Instruct/`：老照片理解
- `Fun-CosyVoice3-0.5B-2512/`：个性化语音合成
- `Wan2.2-TI2V-5B/`：记忆视频生成

逐模型体积见 [`../docs/MODEL_MANIFEST.md`](../docs/MODEL_MANIFEST.md)，逐文件 SHA-256 见 [`../docs/SHA256SUMS.txt`](../docs/SHA256SUMS.txt)。从模型托管平台下载后，请保持上述目录名不变；启动脚本会按这些相对路径查找模型。

项目自行训练的最终 LoRA 适配器体积约 81 MB，已保留在 `train/outputs/sft-1.5b/adapter/`，可随代码仓库一起提交。基础模型和第三方模型应遵守各自许可证，并通过 Hugging Face、ModelScope 或对象存储发布。
