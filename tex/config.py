"""Configuration — loads .env and exposes typed settings."""

import os
from pathlib import Path
from dotenv import load_dotenv


_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)


class Config:
    model: str = os.getenv("TEX_MODEL", "llama3.2")
    temperature: float = float(os.getenv("TEX_TEMPERATURE", "0.1"))
    # Max tokens to generate. JSON tool calls are ~80 tokens; 256 gives buffer.
    # Lower = faster responses. Raise if the model truncates its output.
    max_tokens: int = int(os.getenv("TEX_MAX_TOKENS", "256"))
    log_file: str = os.getenv("TEX_LOG_FILE", "logs/tex.log")
    require_confirm: bool = os.getenv("TEX_CONFIRM", "true").lower() == "true"
    # Maximum character length for a general argument value from the LLM.
    # Raise this if you use a model that produces longer structured outputs.
    max_arg_value_len: int = int(os.getenv("TEX_MAX_ARG_LEN", "1024"))
    # Context window size. Smaller = faster prefill (the initial 'Thinking...'
    # delay). 2048 comfortably fits our system prompt + conversation history.
    # Raise to 4096+ if you use very long multi-turn chat sessions.
    num_ctx: int = int(os.getenv("TEX_NUM_CTX", "2048"))


config = Config()
