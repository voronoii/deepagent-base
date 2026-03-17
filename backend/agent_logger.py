"""Structured colored logging for multi-agent workflow tracing.

Provides visually distinct log output for agent handoffs, tool calls,
tool results, and agent responses to improve observability.

Format:
  [ agent-name ] --- [ ACTION ] --- detail text

  - Agent names: sky blue (ANSI 96)
  - Action types: orange (ANSI 38;5;208), green for results, red for errors
  - Handoffs: preceded by separator line
"""

import logging
import time
from contextvars import ContextVar

logger = logging.getLogger("agent.trace")

# Context variable to track which agent is currently executing
_current_agent: ContextVar[str] = ContextVar("current_agent", default="system")


# -- ANSI Color Codes ---------------------------------------------------------

CYAN = "\033[96m"          # Sky blue - agent names
ORANGE = "\033[38;5;208m"  # Orange - action types
GREEN = "\033[92m"         # Green - success/results
RED = "\033[91m"           # Red - errors
YELLOW = "\033[93m"        # Yellow - warnings/lifecycle
DIM = "\033[2m"            # Dim - secondary info
BOLD = "\033[1m"           # Bold
RESET = "\033[0m"          # Reset all

_SEP_LINE = f"{DIM}{'━' * 70}{RESET}"


# -- Formatting Helpers --------------------------------------------------------

def _agent_box(name: str) -> str:
    return f"{CYAN}[ {name} ]{RESET}"


def _action_box(action: str, color: str = ORANGE) -> str:
    return f"{color}[ {action} ]{RESET}"


def _line(agent: str, action: str, detail: str, action_color: str = ORANGE) -> str:
    return f"{_agent_box(agent)} --- {_action_box(action, action_color)} --- {detail}"


# -- Context Management -------------------------------------------------------

def set_current_agent(name: str) -> None:
    """Set the currently executing agent name (for MCP call attribution)."""
    _current_agent.set(name)


def get_current_agent() -> str:
    """Get the currently executing agent name."""
    return _current_agent.get()


# -- Log Functions -------------------------------------------------------------

def handoff(from_agent: str, to_agent: str, task: str) -> None:
    """Log agent-to-agent handoff with separator."""
    task_preview = task[:120] + "..." if len(task) > 120 else task
    logger.info(_SEP_LINE)
    logger.info(
        _line(from_agent, "HANDOFF",
              f"-> {CYAN}{to_agent}{RESET} : \"{task_preview}\"")
    )


def tool_call(agent: str, tool_name: str, args: dict | str) -> None:
    """Log a tool invocation."""
    args_str = str(args)[:200]
    logger.info(
        _line(agent, "TOOL_CALL", f"{tool_name}({args_str})")
    )


def tool_result(agent: str, tool_name: str, result_length: int,
                elapsed_s: float = 0) -> None:
    """Log a tool result."""
    elapsed_str = f" {DIM}({elapsed_s:.1f}s){RESET}" if elapsed_s > 0 else ""
    logger.info(
        _line(agent, "TOOL_RESULT",
              f"{GREEN}{tool_name}{RESET} -> {result_length} chars{elapsed_str}",
              GREEN)
    )


def response(agent: str, content: str, char_count: int = 0) -> None:
    """Log an agent's text response."""
    preview = content[:100].replace("\n", " ")
    if len(content) > 100:
        preview += "..."
    size_info = f" {DIM}({char_count} chars){RESET}" if char_count else ""
    logger.info(
        _line(agent, "RESPONSE", f"\"{preview}\"{size_info}")
    )


def error(agent: str, error_msg: str) -> None:
    """Log an error."""
    logger.error(
        _line(agent, "ERROR", f"{RED}{error_msg}{RESET}", RED)
    )


def mcp_call(server: str, tool: str, args: dict) -> None:
    """Log an MCP tool call."""
    agent = get_current_agent()
    args_str = str(args)[:200]
    logger.info(
        _line(agent, "MCP_CALL", f"{server}/{tool}({args_str})")
    )


def mcp_result(server: str, tool: str, length: int, preview: str,
               elapsed_s: float = 0) -> None:
    """Log an MCP tool result."""
    agent = get_current_agent()
    elapsed_str = f" {DIM}({elapsed_s:.1f}s){RESET}" if elapsed_s > 0 else ""
    preview_short = preview[:150].replace("\n", " ")
    logger.info(
        _line(agent, "MCP_RESULT",
              f"{GREEN}{server}/{tool}{RESET} -> {length} chars{elapsed_str}"
              f" : \"{preview_short}\"",
              GREEN)
    )


def mcp_error(server: str, tool: str, error_msg: str) -> None:
    """Log an MCP error."""
    agent = get_current_agent()
    logger.error(
        _line(agent, "MCP_ERROR",
              f"{RED}{server}/{tool} : {error_msg}{RESET}", RED)
    )


def token_usage(agent: str, prompt: int, completion: int, total: int,
                max_ctx: int) -> None:
    """Log token usage with context utilization percentage."""
    pct = (prompt / max_ctx * 100) if max_ctx else 0
    color = RED if pct > 80 else (YELLOW if pct > 60 else DIM)
    logger.info(
        _line(agent, "TOKENS",
              f"prompt={prompt} completion={completion} total={total} "
              f"{color}({pct:.0f}% of {max_ctx}){RESET}",
              DIM)
    )


def lifecycle(agent: str, event: str, detail: str = "") -> None:
    """Log agent lifecycle events (INIT, READY, SHUTDOWN, etc.)."""
    detail_str = detail if detail else ""
    logger.info(
        _line(agent, event, detail_str, YELLOW)
    )


# -- Logger Setup --------------------------------------------------------------

def setup_trace_logger() -> None:
    """Configure the agent.trace logger with a minimal timestamp-only format.

    Call this once during application startup (after logging.basicConfig).
    The trace logger uses a short time-only format so the structured
    colored output is the focus, not the boilerplate.
    """
    trace_logger = logging.getLogger("agent.trace")
    trace_logger.setLevel(logging.DEBUG)
    trace_logger.propagate = False  # Don't duplicate to root logger

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        fmt=f"{DIM}%(asctime)s{RESET} %(message)s",
        datefmt="%H:%M:%S",
    ))
    trace_logger.addHandler(handler)
