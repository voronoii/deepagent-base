"""Configuration for DeepAgent backend."""

import os

from langchain_openai import ChatOpenAI

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://10.1.61.227:8002/v1")
VLLM_API_KEY = "dummy"
VLLM_MODEL = "default"

# Agent root directory for FilesystemBackend
AGENT_ROOT_DIR = os.environ.get("AGENT_ROOT_DIR", "/DATA3/users/mj/DeepAgent-Base")

# Memory file path (relative to root_dir for FilesystemBackend)
AGENTS_MD_PATH = "./backend/AGENTS.md"

# vLLM maximum context window size
MAX_CONTEXT_TOKENS = 32768


def get_model(
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> ChatOpenAI:
    """Create vLLM-backed ChatOpenAI model instance.

    Sets ``model.profile["max_input_tokens"]`` so that deepagents'
    ``SummarizationMiddleware`` can calculate the correct trigger threshold
    (85% of context window) instead of falling back to 170k tokens.
    """
    model = ChatOpenAI(
        model=VLLM_MODEL,
        openai_api_base=VLLM_BASE_URL,
        openai_api_key=VLLM_API_KEY,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # Tell deepagents about our actual context window so summarization
    # triggers at 85% of 32768 ≈ 27852 tokens instead of 170000.
    model.profile = {"max_input_tokens": MAX_CONTEXT_TOKENS}
    return model
