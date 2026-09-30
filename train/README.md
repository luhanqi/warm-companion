# 暖伴对话模型 · 训练

**底座：`Qwen/Qwen2.5-1.5B-Instruct`**（LoRA）。不能把旧的 0.5B 适配器接到 1.5B 上。

配置项、每个文件干什么，见 **[文档.md](文档.md)**。

## 一次跑完（需要 NVIDIA 显卡）

本机 **Python 3.12**。不要用暖伴后端那个 3.8 虚拟环境。

```powershell
cd train
.\run_train.ps1
```

或逐步：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cu124
.\.venv\Scripts\python -m pip install -r requirements.txt
python prepare_data.py
python train_sft.py
python eval_model.py
python chat.py --text "今天中午吃了面"
```

没有显卡时加 `-Cpu -Smoke` 只能确认环境，完整 1.5B 会极慢。

改学习率、产出目录：编辑 `config.yaml`。底座优先从 ModelScope 下载；失败则打开  
https://www.modelscope.cn/models/Qwen/Qwen2.5-1.5B-Instruct  
下载后：`python train_sft.py --model 本地文件夹`

可选对比学习（先试聊 SFT，再决定要不要 DPO）：

```powershell
python train_dpo.py
```

## 接到暖伴后端

另开终端：

```powershell
cd train
.\.venv\Scripts\Activate.ps1
python serve.py
```

在 `backend/.env` 写入：

```
LLM_API_KEY=local
LLM_BASE_URL=http://127.0.0.1:8001/v1
LLM_MODEL=nuanban
```

然后照常 `npm run server`。后端仍是 Python 3.8，不必把 torch 装进 `backend/.venv`。

## 产出

- `outputs/sft-1.5b/adapter/`  默认 LoRA，给 `chat.py` / `serve.py` / `eval_model.py` 用
- `python export_merge.py`  合成完整权重到 `outputs/merged-1.5b/`
