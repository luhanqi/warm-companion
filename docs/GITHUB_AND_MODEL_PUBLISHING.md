# GitHub 与模型发布说明

## GitHub 代码仓库包含什么

代码仓库包含前端、后端、训练代码、模型服务、部署文件、文档和最终 LoRA 适配器。以下内容按安全与体积要求排除：

- 基础模型和第三方模型权重（约 55 GB）
- 可重新创建的 Python 运行环境和下载缓存（`runtime/`）
- API 密钥、生产环境变量、数据库、用户照片、录音、日志和 PID

最终 LoRA 适配器位于 `train/outputs/sft-1.5b/adapter/`。LoRA 和演示音频使用 Git LFS 管理，避免较大的二进制文件导致普通 Git 推送超时。

克隆后请执行：

```powershell
git lfs install
git lfs pull
```

## 为什么不能把全部权重直接放进 GitHub

当前模型目录约 55 GB，其中 9 个文件超过 2 GB，最大文件约 10.58 GB。GitHub 普通 Git 文件上限为 100 MB；Git LFS 也有单文件和账户存储/流量配额，不适合作为本项目全部基础模型的分发渠道。

推荐发布方式：

1. GitHub：源代码、文档、最终 LoRA 适配器和演示音频；二进制文件使用 Git LFS。
2. Hugging Face 或 ModelScope：允许再分发的模型权重及 LoRA。
3. 对象存储：完整比赛离线包，生成带有效期的下载链接。
4. 在 GitHub Release 或 README 中只提供下载链接、目录结构与 SHA-256，不提交权重本体。

## 恢复完整本地环境

1. 克隆 GitHub 代码仓库。
2. 按 `docs/MODEL_MANIFEST.md` 下载模型到 `models/` 对应目录。
3. 使用 `docs/SHA256SUMS.txt` 校验文件完整性。
4. 按根目录 `README.md` 重建或使用 Python 环境。
5. 使用 `start-with-models.ps1 -Profile standard` 启动推荐模型组合。

不要公开上传 `.env`、`.env.production`、SQLite 数据库、用户媒体或云服务器密码。
