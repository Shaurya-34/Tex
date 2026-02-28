"""Configuration — loads .env and exposes typed settings."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (walk up from this file)
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)


class Config:
    model: str = os.getenv("TEX_MODEL", "llama3.2")
    temperature: float = float(os.getenv("TEX_TEMPERATURE", "0.1"))
    max_tokens: int = int(os.getenv("TEX_MAX_TOKENS", "512"))
    log_file: str = os.getenv("TEX_LOG_FILE", "logs/tex.log")
    require_confirm: bool = os.getenv("TEX_CONFIRM", "true").lower() == "true"


config = Config()
