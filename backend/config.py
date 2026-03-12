"""Configuration for DeepAgent backend."""

import os

from langchain_openai import ChatOpenAI

# ── Model provider selection ─────────────────────────────────
MODEL_TYPE = os.environ.get("MODEL_TYPE", "vllm")  # "vllm" | "openai"

# ── OpenAI settings ──────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
OPENAI_MAX_CONTEXT_TOKENS = 128_000

# ── vLLM settings ────────────────────────────────────────────
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://10.1.61.227:8002/v1")
VLLM_API_KEY = "dummy"
VLLM_MODEL = "default"
VLLM_MAX_CONTEXT_TOKENS = 32_768

# ── Common settings ──────────────────────────────────────────
AGENT_ROOT_DIR = os.environ.get("AGENT_ROOT_DIR", "/DATA3/users/mj/DeepAgent-Base")
AGENTS_MD_PATH = "./backend/AGENTS.md"

# Dynamic context window based on selected model
MAX_CONTEXT_TOKENS = OPENAI_MAX_CONTEXT_TOKENS if MODEL_TYPE == "openai" else VLLM_MAX_CONTEXT_TOKENS


def get_model(
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> ChatOpenAI:
    """Create ChatOpenAI model instance for the configured provider.

    Sets ``model.profile["max_input_tokens"]`` so that deepagents'
    ``SummarizationMiddleware`` can calculate the correct trigger threshold
    (85% of context window) instead of falling back to 170k tokens.
    """
    if MODEL_TYPE == "openai":
        model = ChatOpenAI(
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    else:
        model = ChatOpenAI(
            model=VLLM_MODEL,
            openai_api_base=VLLM_BASE_URL,
            openai_api_key=VLLM_API_KEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    model.profile = {"max_input_tokens": MAX_CONTEXT_TOKENS}
    return model
