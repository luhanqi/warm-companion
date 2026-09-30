# 暖伴（Warm Companion）比赛提交包

暖伴是一套面向老年人与家属的认知陪伴系统。本提交包包含前端、后端、训练代码、最终 LoRA 适配器、离线模型和部署说明；不包含真实账号、数据库、用户照片、录音、日志或 API 密钥。

## 三项核心创新

1. **无感式认知健康监测**：在自然对话中统计语言流畅度、词汇丰富度、重复率、叙事连贯度等趋势，并向家属端提供研究型风险提示。该结果不是医学诊断。
2. **私人记忆增强**：将回忆录、照片说明、家庭事件等写入私有记忆库，使用向量检索与重排为对话提供个人经历上下文；自训练 LoRA 适配器用于暖伴式陪伴表达。
3. **记忆时光机**：把老照片、语音口述、个性化语音和视频生成串联为可回看的记忆内容。

## 目录说明

| 路径 | 作用 |
| --- | --- |
| `backend/` | FastAPI 后端、数据库、登录注册、对话、认知趋势、RAG、绘画及多模态接口 |
| `web/` | 老人端与家人端全部网页、脚本、样式、图片和音频资源 |
| `model-services/` | 语音识别、语义检索、重排、照片理解及模型启停服务 |
| `train/` | 数据准备、SFT/DPO 训练、评估、推理服务和最终 LoRA 适配器 |
| `models/` | 已下载的本地基础模型与多模态模型 |
| `runtime/` | 已建立的后端、通用模型、CosyVoice Python 环境及 CosyVoice 官方推理代码 |
| `tools/` | 提交包校验工具；FFmpeg 可执行程序需按下文单独安装 |
| `docs/` | 架构、模型清单、原始模型配置说明、文件清单和整理日志 |
| `.env.example` | 不含密钥的环境变量模板 |
| `start-with-models.ps1` | 启动本地模型服务后再启动后端 |
| `Dockerfile`、`docker-compose.prod.yml` | 云端部署配置 |
| `package.json`、`vite.config.ts` | 前端开发与构建配置 |

## 主要源文件作用

### 后端

- `backend/run.py`：后端启动入口，默认端口 8002。
- `backend/app/main.py`：API 路由、静态页面与服务编排。
- `backend/app/auth.py`：注册、登录、会话与权限校验。
- `backend/app/db.py`：数据库结构、连接和初始化。
- `backend/app/llm.py`：本地 OpenAI 兼容服务或云端大模型调用。
- `backend/app/embeddings.py`：记忆向量化和重排调用。
- `backend/app/cognition.py`：日常对话认知特征和趋势逻辑。
- `backend/app/cognition_eval.py`、`evalset.py`：认知模块评估。
- `backend/app/model_services.py`：语音、视觉、个性化音色、视频和研究模型连接。
- `backend/app/paint.py`：绘画供应商选择、提示词和生成流程。
- `backend/app/media.py`：照片、录音、视频等媒体处理。
- `backend/app/life.py`、`content.py`：生活内容和业务数据。
- `backend/app/agents.py`、`blackboard.py`：多模块协作状态。
- `backend/app/extract.py`、`page_command.py`：信息抽取与页面命令。
- `backend/tests/`：创新功能和流式上下文自动测试。

### 模型服务

- `speech_service.py`：SenseVoice 语音识别和 FSMN-VAD。
- `rag_service.py`：BGE-M3 向量与 BGE reranker 重排服务。
- `vision_service.py`：Qwen2-VL 老照片理解。
- `cosyvoice_bridge.py`：CosyVoice 个性化语音桥接。
- `start-local-models.ps1`、`stop-local-models.ps1`：本地附加模型启停。
- `start-original-chat.ps1`、`stop-original-chat.ps1`：自训练对话模型启停。
- `start-cosyvoice.ps1`、`stop-cosyvoice.ps1`：个性化音色模型启停。
- `download_wan.py`、`start-wan-download.ps1`、`wan-download-status.ps1`：Wan 模型下载与状态检查（模型已经包含，通常无需重下）。

### 训练

- `build_seed.py`、`prepare_data.py`：构建并划分训练数据。
- `train_sft.py`、`train_dpo.py`：监督微调和偏好训练。
- `eval_model.py`：训练结果评估。
- `export_merge.py`：合并导出模型。
- `serve.py`：将本地模型暴露为 OpenAI 兼容接口。
- `resolve_model.py`：优先寻找提交包内的基础模型。
- `prompt.py`、`settings.py`、`config.yaml`：提示词和训练参数。
- `outputs/sft-1.5b/adapter/`：比赛使用的最终 LoRA 适配器。

### 前端页面

- `login.html`、`register.html`：登录注册。
- `index.html`、`garden.html`：入口与老人端主页。
- `talk.html`：陪伴对话与语音采集。
- `memoir.html`、`nostalgia.html`、`memory.html`：回忆录、怀旧内容和私人记忆。
- `paint.html`：语音/文字绘画。
- `life.html`、`games.html`：生活内容与益智活动。
- `family.html`、`care.html`、`gift.html`、`observe.html`：家人端、照料寄画与观察台。
- `profile.html`：用户资料与设置。
- `web/js/`、`web/css/`、`web/images/`、`web/audio/`：页面逻辑、样式和相对路径资源。

## 快速运行（基础演示）

要求 Windows 10/11。当前文件夹已经包含本机可用的 Python 环境；重新安装时需要 Python 3.10/3.11，前端开发构建另需 Node.js 18+。

涉及音视频转码时还需要安装 FFmpeg，并确保终端执行 `ffmpeg -version` 能正常返回。本提交包中的 `tools/ffmpeg/` 是预留目录，不包含第三方可执行程序。

```powershell
cd D:\warm-companion-competition\FINAL_READY
.\start-backend.ps1
```

浏览器访问 `http://127.0.0.1:8002/`。数据库会在首次启动时自动创建；提交包未附带任何真实用户数据库。

首次使用请先注册账号；注册成功后系统会返回登录页，需要使用刚注册的账号和密码重新登录。项目不附带、也不会在登录页展示预设账号和密码。

直接运行 `backend/run.py` 默认不会自动拉起模型，因此不会反复重连或抢占端口。若使用 `backend/.env`，保持：

```env
NUANBAN_AUTO_START_MODELS=0
```

随后填写自己合法取得的 DeepSeek/硅基流动等 API 密钥即可演示云端能力。不要把填写密钥后的 `.env` 提交给评委或上传代码仓库。

## Docker 云端部署

低配云服务器只部署网页、后端和数据库，不在容器中加载本地大模型：

```powershell
Copy-Item .env.production.example .env.production
docker compose -f docker-compose.prod.yml up -d --build
```

按需要编辑 `.env.production` 中的 API 地址和密钥。`persistent-data/` 用于保存数据库和用户上传，升级容器时不要删除。Docker 构建已排除 `models/`，避免把约 55 GB 权重发送进构建上下文。

## 本地模型运行

已准备好的环境分别位于 `runtime/model-env/` 与 `runtime/cosyvoice-env/`。推荐按电脑能力选择启动档：

```powershell
# 16 GB 电脑的稳定档：自训练对话 + SenseVoice/openSMILE + BGE RAG + 后端
.\start-with-models.ps1 -Profile standard

# 单独使用照片理解 + 后端（先停止上一档）
.\start-with-models.ps1 -Profile vision

# 单独使用个性化音色 + 后端（先停止上一档）
.\start-with-models.ps1 -Profile cosyvoice
```

需要重新创建通用模型环境时：

```powershell
python -m venv runtime\model-env
runtime\model-env\Scripts\python -m pip install -r model-services\requirements-speech.txt -r model-services\requirements-rag.txt -r model-services\requirements-vision.txt -r train\requirements.txt
```

启动脚本会同时识别 Conda 环境根目录的 `python.exe` 和标准 venv 的 `Scripts/python.exe`。

本地服务默认端口：对话 8001、后端 8002、语音 8003、RAG 8004、视觉 8005、CosyVoice 50000。模型启动脚本会先确认健康接口，端口被旧进程占用时不会再重复启动。

`-Profile all` 只用于高内存工作站；它会启动上述可执行服务，但仍不包含 Wan 视频。16 GB 电脑同时实际加载对话、RAG、语音、视觉和 CosyVoice 会超过 30 GB 内存并导致视觉进程被系统终止，不应作为日常启动方式。

## 本机实测结果

| 功能 | 模型/服务 | 结果 |
| --- | --- | --- |
| 暖伴对话 | Qwen2.5-1.5B + 最终 LoRA | 已生成中文陪伴回复 |
| 私人记忆检索 | BGE-M3 | 已返回 1024 维向量 |
| 记忆重排 | BGE-reranker-v2-m3 | 已把匹配的个人经历排在首位 |
| 语音识别 | SenseVoiceSmall + FSMN-VAD | 已完成本地转写 |
| 声学指标 | openSMILE + 停顿分析 | 已返回静音比例、停顿次数和最长停顿 |
| 老照片理解 | Qwen2-VL-2B | 单独运行时已正确描述测试照片 |
| 个性化音色 | Fun-CosyVoice3-0.5B | 已生成有效 WAV 音频 |
| 绘画 | Pollinations | 已返回有效 JPEG；该项依赖互联网，不是本地权重 |
| 记忆视频 | Wan2.2-TI2V-5B | 权重完整；本机无 24 GB NVIDIA 显卡，未做生成测试 |

## 硬件说明

- 后端、网页和基础数据库可以在普通电脑运行。
- BGE、SenseVoice 可使用 CPU；Qwen2-VL、CosyVoice 和 1.5B 对话模型在 CPU 上可单独运行，但同时加载会大量使用页面文件。
- Wan2.2-TI2V-5B 体积约 32 GB，官方 TI2V 推理要求至少 24 GB NVIDIA 显存。本机没有可用 NVIDIA 显卡，所以只能保存和校验权重，不能实际生成视频。2 核 2 GB 云服务器也不能承载这些本地模型。
- 资源不足时可仅启动后端，将模型服务放在本地 GPU 电脑或独立推理服务器。

## 数据和安全

- 已排除：`.env`、SQLite 数据库、上传照片/录音、运行日志、PID、缓存、虚拟环境、模型下载缓存和重复检查点。
- 所有页面资源使用提交包内部的相对路径。
- `.env.example` 只含占位符，不含真实密钥。
- `.env.production.example` 是 Docker 部署模板；使用时复制为 `.env.production`，真实文件不要提交。
- 认知趋势仅用于研究和陪伴提示，不作医疗诊断。

完整模型尺寸见 `docs/MODEL_MANIFEST.md`；逐文件大小和 SHA-256 见 `docs/FILE_MANIFEST.csv` 与 `docs/SHA256SUMS.txt`。

## GitHub 与模型发布

GitHub 仓库用于保存源代码、网页、训练脚本、部署文件、文档和最终 LoRA 适配器。约 55 GB 的基础模型与第三方模型不会直接提交到 GitHub：当前有 9 个权重文件超过 2 GB，最大文件约 10.58 GB，超过 GitHub/Git LFS 的实际发布限制。

模型权重请发布到 Hugging Face、ModelScope 或对象存储，并保持 `models/` 下的目录名不变。代码仓库已保留 `models/README.md`、`docs/MODEL_MANIFEST.md` 和逐文件 SHA-256，下载模型后可以恢复完整离线项目。详细方案见 `docs/GITHUB_AND_MODEL_PUBLISHING.md`。
