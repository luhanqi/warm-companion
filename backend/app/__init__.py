# 暖伴第一阶段后端
"""Warm Companion backend package configuration.

The normal application secrets remain in ``backend/.env``.  Local model
endpoints live in the ignored ``backend/.env.models.local`` file so enabling
downloaded models never overwrites a user's API keys.
"""
from pathlib import Path

from dotenv import load_dotenv


_BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_BACKEND_DIR / ".env.models.local", override=True)
