# -*- coding: utf-8 -*-
"""OpenAI 兼容接口，给暖伴后端直接用。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from peft import PeftModel
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
from threading import Thread

from resolve_model import resolve_model
from settings import load_config

ADAPTER = Path(load_config()["sft_output"]) / "adapter"


class Msg(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    model: str = "nuanban"
    messages: List[Msg]
    stream: bool = True
    temperature: float = 0.7


def load_model(adapter: Path):
    meta = json.loads((adapter / "nuanban_meta.json").read_text(encoding="utf-8"))
    base_id = meta["base_model"]
    base_path = resolve_model(base_id)
    # Load tokenizer metadata from the base checkpoint.  Some older exported
    # adapters store ``extra_special_tokens`` as a list, while current
    # Transformers expects a mapping and refuses to start the service.
    tok = AutoTokenizer.from_pretrained(base_path, trust_remote_code=True, local_files_only=True)
    adapter_template = adapter / "chat_template.jinja"
    if adapter_template.exists():
        tok.chat_template = adapter_template.read_text(encoding="utf-8")
    cpu = not torch.cuda.is_available()
    base = AutoModelForCausalLM.from_pretrained(
        base_path,
        trust_remote_code=True,
        torch_dtype=torch.float32 if cpu else torch.float16,
        device_map={"": "cpu"} if cpu else "auto",
    )
    # PEFT otherwise re-runs automatic placement when the base model lives on
    # CPU and may demand a disk offload directory even for this small model.
    model = PeftModel.from_pretrained(
        base,
        str(adapter),
        device_map={"": "cpu"} if cpu else "auto",
    )
    model.eval()
    return tok, model


def build_app(adapter: Path) -> FastAPI:
    tok, model = load_model(adapter)
    app = FastAPI(title="暖伴本地对话")

    def _gen(messages, temperature: float):
        chat = [{"role": m.role, "content": m.content} for m in messages]
        text = tok.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
        inputs = tok(text, return_tensors="pt")
        device = next(model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)
        kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=120,
            do_sample=True,
            temperature=max(0.1, temperature),
            top_p=0.9,
            eos_token_id=tok.eos_token_id,
            pad_token_id=tok.eos_token_id,
        )
        thread = Thread(target=model.generate, kwargs=kwargs)
        thread.start()
        for piece in streamer:
            yield piece
        thread.join()

    @app.get("/health")
    def health():
        return {"ok": True, "model": "nuanban-local"}

    @app.post("/v1/chat/completions")
    def chat(payload: ChatIn):
        if not payload.stream:
            text = "".join(_gen(payload.messages, payload.temperature))
            return {
                "choices": [{"message": {"role": "assistant", "content": text}}]
            }

        def event_stream():
            for piece in _gen(payload.messages, payload.temperature):
                chunk = {
                    "choices": [{"delta": {"content": piece}, "index": 0}]
                }
                yield "data: %s\n\n" % json.dumps(chunk, ensure_ascii=False)
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", default=str(ADAPTER))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    app = build_app(Path(args.adapter))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
