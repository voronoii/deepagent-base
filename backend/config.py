"""Configuration for DeepAgent backend."""

import os

from langchain_openai import ChatOpenAI

# ── Model provider selection ─────────────────────────────────
MODEL_TYPE = os.environ.get("MODEL_TYPE", "vllm")  # "vllm" | "openai"

# ── OpenAI settings ──────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")
OPENAI_MODEL_MINI = os.environ.get("OPENAI_MODEL_MINI", "gpt-5-mini")

OPENAI_MAX_CONTEXT_TOKENS = 128_000

# ── Local Model settings ────────────────────────────────────────────
LOCAL_BASE_URL = os.environ.get("LOCAL_BASE_URL", "http://10.1.61.229:11001/v1")
LOCAL_API_KEY = "dummy"
LOCAL_MODEL = os.environ.get("LOCAL_MODEL", "/model")
LOCAL_MAX_CONTEXT_TOKENS = 32_768

# ── Common settings ──────────────────────────────────────────
AGENT_ROOT_DIR = os.environ.get("AGENT_ROOT_DIR", "/DATA3/users/mj/DeepAgent-Base")
AGENTS_MD_PATH = "./backend/config/AGENTS.md"
SKILLS_DIR = "./backend/skills/"

# Dynamic context window based on selected model
MAX_CONTEXT_TOKENS = OPENAI_MAX_CONTEXT_TOKENS if MODEL_TYPE == "openai" else LOCAL_MAX_CONTEXT_TOKENS


def get_model(
    model_type: str = "openai",
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> ChatOpenAI:
    """Create ChatOpenAI model instance for the configured provider.

    Sets ``model.profile["max_input_tokens"]`` so that deepagents'
    ``SummarizationMiddleware`` can calculate the correct trigger threshold
    (85% of context window) instead of falling back to 170k tokens.
    """
    if model_type == "openai":
        model = ChatOpenAI(
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    elif model_type == "openai_mini":
        model = ChatOpenAI(
            model=OPENAI_MODEL_MINI,
            api_key=OPENAI_API_KEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    elif model_type == "oss":
        model = ChatOpenAI(
            model=LOCAL_MODEL,
            openai_api_base=LOCAL_BASE_URL,
            openai_api_key=LOCAL_API_KEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    else:
        model = ChatOpenAI(
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    

    model.profile = {"max_input_tokens": MAX_CONTEXT_TOKENS}
    return model
