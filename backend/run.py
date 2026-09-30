import sys
import os
import subprocess
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))


def start_model_services() -> None:
    """Make the normal backend command bring up its local model dependencies."""
    # Starting every model implicitly made a normal backend launch compete for
    # ports and memory.  Use start-with-models.ps1 when model startup is wanted.
    if os.getenv("NUANBAN_AUTO_START_MODELS", "0").strip().lower() in {"0", "false", "no"}:
        return
    scripts = [
        (PROJECT_ROOT / "model-services" / "start-original-chat.ps1", 240),
        (PROJECT_ROOT / "model-services" / "start-local-models.ps1", 90),
    ]
    for script, timeout in scripts:
        try:
            subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                cwd=str(PROJECT_ROOT),
                check=True,
                timeout=timeout,
            )
        except Exception as exc:
            # The web backend still has safe fallbacks, so keep it available and
            # print a concrete startup warning instead of aborting the whole app.
            print(f"本地模型自动启动失败（{script.name}）：{exc}")

if __name__ == "__main__":
    start_model_services()
    reload_enabled = os.getenv("NUANBAN_RELOAD", "").strip() == "1"
    port = int(os.getenv("NUANBAN_PORT", "8002"))
    host = os.getenv("NUANBAN_HOST", "127.0.0.1").strip() or "127.0.0.1"
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        reload_dirs=[str(ROOT)] if reload_enabled else None,
    )
