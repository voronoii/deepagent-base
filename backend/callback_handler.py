"""Logging hooks for real-time agent trace visibility.

Two complementary mechanisms:

1. AgentTraceCallbackHandler (LangChain AsyncCallbackHandler)
   - Attaches to inner_agent.ainvoke(config={"callbacks": [handler]})
   - Captures orchestrator-level LLM/tool events in real-time

2. TracingMiddleware (deepagents AgentMiddleware)
   - Added to subagent specs via middleware=[TracingMiddleware("name")]
   - Captures sub-agent internal LLM calls and tool calls
   - No deepagents source modification required
"""

import ast
import json
import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, LLMResult
from langchain.agents.middleware.types import AgentMiddleware

from backend import agent_logger

logger = logging.getLogger(__name__)


class AgentTraceCallbackHandler(AsyncCallbackHandler):
    """Real-time callback handler that logs agent events via agent_logger.

    Attach to ``inner_agent.ainvoke(config={"callbacks": [handler]})``
    to get real-time terminal logs for LLM generation, tool calls, and
    chain transitions.
    """

    def __init__(self, agent_name: str = "orchestrator"):
        super().__init__()
        self.agent_name = agent_name
        # run_id -> chain/node name for resolving which agent is active
        self._chain_names: dict[str, str] = {}

    # ------------------------------------------------------------------
    # LLM events
    # ------------------------------------------------------------------

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log when a chat model starts generating."""
        model_name = (
            serialized.get("kwargs", {}).get("model_name", "")
            or serialized.get("kwargs", {}).get("model", "")
        )
        if not model_name:
            id_parts = serialized.get("id", [])
            model_name = id_parts[-1] if id_parts else "unknown"

        agent = self._resolve_agent(parent_run_id)
        agent_logger.lifecycle(agent, "LLM_START", f"model={model_name}")

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Log when an LLM finishes generating."""
        agent = self._resolve_agent(parent_run_id)

        # Extract token usage if available
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            if usage:
                agent_logger.token_usage(
                    agent,
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    usage.get("total_tokens", 0),
                    32768,
                )
                return

        agent_logger.lifecycle(agent, "LLM_END", "")

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Log LLM error."""
        agent = self._resolve_agent(parent_run_id)
        agent_logger.error(agent, f"LLM error: {error}")

    # ------------------------------------------------------------------
    # Tool events
    # ------------------------------------------------------------------

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log tool call start — detect subagent handoffs via 'task' tool."""
        tool_name = serialized.get("name", "unknown")
        agent = self._resolve_agent(parent_run_id)

        if tool_name == "task":
            try:
                if isinstance(input_str, str):
                    try:
                        args = json.loads(input_str)
                    except json.JSONDecodeError:
                        args = ast.literal_eval(input_str)
                else:
                    args = input_str
                subagent_type = args.get("subagent_type", "agent")
                description = args.get("description", "")
                agent_logger.handoff(agent, subagent_type, description)
                agent_logger.set_current_agent(subagent_type)
            except Exception:
                agent_logger.handoff(agent, "unknown-agent", str(input_str)[:120])
        else:
            agent_logger.tool_call(agent, tool_name, str(input_str)[:200])

    async def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        name: str | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Log tool completion."""
        agent = self._resolve_agent(parent_run_id)
        result_str = str(output)
        tool_name = name or "tool"

        if tool_name == "task":
            # Subagent returned — log as response
            agent_logger.response(agent, result_str, len(result_str))
        else:
            agent_logger.tool_result(agent, tool_name, len(result_str))

        # Reset current agent back to orchestrator
        agent_logger.set_current_agent(self.agent_name)

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Log tool error."""
        agent = self._resolve_agent(parent_run_id)
        agent_logger.error(agent, f"Tool error: {error}")
        agent_logger.set_current_agent(self.agent_name)

    # ------------------------------------------------------------------
    # Chain events (for node/agent tracking)
    # ------------------------------------------------------------------

    async def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Track chain/node names for agent resolution."""
        if serialized is None:
            return
        name = serialized.get("name", "")
        if name:
            self._chain_names[str(run_id)] = name

    async def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Clean up chain tracking."""
        self._chain_names.pop(str(run_id), None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_agent(self, parent_run_id: UUID | None) -> str:
        """Resolve the currently executing agent from chain context."""
        if parent_run_id:
            return self._chain_names.get(str(parent_run_id), self.agent_name)
        return self.agent_name


# ======================================================================
# TracingMiddleware — deepagents AgentMiddleware for sub-agent internals
# ======================================================================


class TracingMiddleware(AgentMiddleware):
    """Deepagents middleware that logs LLM and tool events inside sub-agents.

    Add to subagent specs to get real-time visibility into sub-agent
    internals without modifying the deepagents package::

        research_agent_spec["middleware"] = [TracingMiddleware("research-agent")]

    Hooks used:
        - before_model / after_model: LLM call start/end
    """

    def __init__(self, agent_name: str):
        super().__init__()
        self.agent_name = agent_name
        self.tools = []
        self._llm_start_time: float | None = None

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Log when a sub-agent's LLM starts generating."""
        agent_logger.set_current_agent(self.agent_name)
        agent_logger.lifecycle(self.agent_name, "LLM_START", "")
        self._llm_start_time = time.monotonic()
        return None

    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Log when a sub-agent's LLM finishes generating."""
        elapsed = 0.0
        if self._llm_start_time is not None:
            elapsed = time.monotonic() - self._llm_start_time
            self._llm_start_time = None
        agent_logger.lifecycle(
            self.agent_name, "LLM_END", f"elapsed={elapsed:.1f}s" if elapsed else ""
        )
        return None
