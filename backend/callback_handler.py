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
import os
import re
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGenerationChunk, LLMResult
from collections.abc import Callable
from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse

from backend import agent_logger
from backend.config import get_model

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
    


class LawVerificationMiddleware(AgentMiddleware):
    """Post-response law verification middleware for risk-assessment agents.

    Uses ``wrap_model_call`` to intercept the **final** model response
    (i.e. one without ``tool_calls``).  When the response cites Korean
    statutes the middleware:

    1. Extracts specific law references via regex
       (e.g. "민법 제623조", "주택임대차보호법 제3조의2")
    2. Queries the hug-rag MCP server (domain="law") for each reference
    3. Asks a lightweight LLM to compare the citations against the RAG
       results and **correct only the inaccurate parts** — leaving the
       rest of the response untouched
    4. Returns the corrected ``ModelResponse`` so the UI sees a single,
       verified answer

    Non-final responses (tool-call requests) pass through untouched so
    the normal agent loop is not disrupted.
    """

    # ── Detection: "does this text cite any law at all?" ──────────
    _LAW_DETECT_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"제\d+조(?:의\d+)?"),
        re.compile(r"[가-힣]{2,}(?:보호법|특별법|기본법|특례법)"),
        re.compile(r"[가-힣]{2,}(?:시행령|시행규칙)"),
        re.compile(r"(?:민법|상법|형법|헌법)"),
    ]

    # ── Extraction: pull out "법령명 제N조…" references ────────────
    _LAW_REF_PATTERN: re.Pattern[str] = re.compile(
        r"("
        r"(?:민법|상법|형법|헌법"
        r"|주택임대차보호법"
        r"|상가건물\s*임대차보호법"
        r"|약관의\s*규제에\s*관한\s*법률"
        r"|부동산등기법"
        r"|전세사기피해자\s*지원\s*및\s*피해방지\s*특별법"
        r"|[가-힣]{2,}(?:보호법|특별법|기본법|특례법|시행령|시행규칙))"
        r"\s*제\d+조(?:의\d+)?"
        r"(?:\s*제\d+항)?"
        r"(?:\s*제\d+호)?"
        r")"
    )

    # ── Correction prompt ─────────────────────────────────────────
    _CORRECTION_PROMPT: str = (
        "당신은 법률 검증 전문가입니다. "
        "아래 '원본 응답'에서 인용된 법령을 'RAG 검증 결과'와 비교하세요.\n\n"
        "## 규칙\n"
        "1. 법령 조항의 내용이 RAG 결과와 다르면 RAG 결과 기준으로 "
        "해당 부분**만** 수정하세요.\n"
        "2. RAG에서 찾을 수 없는 법령은 해당 인용 뒤에 "
        "'(※ 정확성 미검증)' 을 표기하세요.\n"
        "3. 법령과 무관한 분석·구조·표현은 **절대 수정하지 마세요.**\n"
        "4. 수정된 전체 응답**만** 출력하세요. "
        "설명·메타 코멘트·검증 보고는 포함하지 마세요.\n\n"
        "## 원본 응답\n{response}\n\n"
        "## RAG 검증 결과\n{rag_results}\n"
    )

    # ── MCP endpoint (docker default) ─────────────────────────────
    _HUG_RAG_URL: str = os.environ.get(
        "HUG_RAG_MCP_URL", "http://mcp-hug-rag:1883/mcp"
    )

    def __init__(self, agent_name: str = "risk-assessment-agent"):
        super().__init__()
        self.agent_name = agent_name
        self._verify_model = get_model("openai_mini",temperature=0.0, max_tokens=8192)

    # ── helpers: detection / extraction ───────────────────────────

    @staticmethod
    def _contains_law_references(text: str) -> bool:
        return any(
            p.search(text) for p in LawVerificationMiddleware._LAW_DETECT_PATTERNS
        )

    @staticmethod
    def _extract_law_references(text: str) -> list[str]:
        """Return deduplicated law-reference strings for RAG queries."""
        refs = LawVerificationMiddleware._LAW_REF_PATTERN.findall(text)
        seen: set[str] = set()
        unique: list[str] = []
        for ref in refs:
            norm = re.sub(r"\s+", " ", ref.strip())
            if norm not in seen:
                seen.add(norm)
                unique.append(norm)
        return unique

    # ── helpers: response inspection ─────────────────────────────

    @staticmethod
    def _is_final_response(response: ModelResponse) -> bool:
        """True when the model produced a final answer (no tool calls)."""
        msg = (
            response
            if isinstance(response, AIMessage)
            else getattr(response, "message", response)
        )
        return not getattr(msg, "tool_calls", None)

    @staticmethod
    def _get_text(response: ModelResponse) -> str:
        msg = (
            response
            if isinstance(response, AIMessage)
            else getattr(response, "message", response)
        )
        return getattr(msg, "content", "") or ""

    @staticmethod
    def _replace_text(response: ModelResponse, new_text: str) -> ModelResponse:
        """Return a copy of *response* with content replaced."""
        if isinstance(response, AIMessage):
            return response.model_copy(update={"content": new_text})
        inner = getattr(response, "message", None)
        if inner is not None and isinstance(inner, AIMessage):
            new_inner = inner.model_copy(update={"content": new_text})
            try:
                return response.__class__(message=new_inner)
            except Exception:
                pass
        return response

    # ── RAG search ───────────────────────────────────────────────

    async def _search_rag(self, queries: list[str]) -> str:
        """Query hug-rag MCP for each law reference; return formatted text."""
        # Lazy import — the mcp client may not be installed everywhere
        try:
            from mcp.client.streamable_http import streamablehttp_client
            from mcp import ClientSession
        except ImportError:
            logger.warning("mcp client SDK unavailable — skipping RAG verification")
            return ""

        fragments: list[str] = []
        try:
            async with streamablehttp_client(url=self._HUG_RAG_URL) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    for query in queries:
                        try:
                            result = await session.call_tool(
                                "search_hug_docs",
                                arguments={
                                    "query_text": query,
                                    "domain": "law",
                                    "limit": 2,
                                    "use_reranker": False,
                                },
                            )
                            content = (
                                result.content[0].text if result.content else "{}"
                            )
                            parsed = json.loads(content)
                            for item in parsed.get("결과", []):
                                fragments.append(
                                    f"[검색어: {query}]\n"
                                    f"  법령: {item.get('문서제목', 'N/A')} "
                                    f"{item.get('조문/섹션명', '')}\n"
                                    f"  내용: {item.get('조문/섹션내용', '')}"
                                )
                        except Exception as exc:
                            logger.warning("RAG lookup failed for %r: %s", query, exc)
        except Exception as exc:
            logger.error("hug-rag MCP connection failed: %s", exc)
            return ""

        return "\n\n".join(fragments)

    # ── LLM correction ───────────────────────────────────────────

    async def _correct_with_llm(
        self, response_text: str, rag_results: str
    ) -> str:
        """Ask an LLM to fix law inaccuracies; returns corrected text."""
        prompt = self._CORRECTION_PROMPT.format(
            response=response_text,
            rag_results=rag_results,
        )
        try:
            result = await self._verify_model.ainvoke(prompt)
            return result.content
        except Exception as exc:
            logger.error("Verification LLM call failed: %s", exc)
            return ""

    # ── main hooks ───────────────────────────────────────────────

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable,
    ) -> ModelResponse:
        """Async wrap: verify & correct law references on final responses."""
        agent_logger.lifecycle(self.agent_name, "VERIFY", "awrap_model_call 진입")
        response = await handler(request)

        is_final = self._is_final_response(response)
        agent_logger.lifecycle(
            self.agent_name, "VERIFY",
            f"is_final={is_final}, type={type(response).__name__}, "
            f"tool_calls={getattr(response, 'tool_calls', 'N/A')}"
        )

        # Pass through non-final (tool-call) responses untouched
        if not is_final:
            return response

        text = self._get_text(response)
        if not text or not self._contains_law_references(text):
            return response

        refs = self._extract_law_references(text)
        if not refs:
            return response

        # -- verification pipeline --
        agent_logger.lifecycle(
            self.agent_name, "VERIFY", f"법령 {len(refs)}건 RAG 검증 시작"
        )

        rag_results = await self._search_rag(refs)
        if not rag_results:
            agent_logger.lifecycle(
                self.agent_name, "VERIFY", "RAG 결과 없음 — 원본 유지"
            )
            return response

        agent_logger.lifecycle(self.agent_name, "VERIFY", "LLM 보정 중")
        corrected = await self._correct_with_llm(text, rag_results)

        if corrected and corrected.strip() != text.strip():
            agent_logger.lifecycle(self.agent_name, "VERIFY", "법령 보정 완료")
            return self._replace_text(response, corrected)

        agent_logger.lifecycle(
            self.agent_name, "VERIFY", "검증 완료 — 수정 없음"
        )
        return response

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable,
    ) -> ModelResponse:
        """Sync fallback — passes through without verification.

        The async version (``awrap_model_call``) performs the actual
        verification.  If the runtime only supports sync calls this
        hook lets the response through unchanged.
        """
        agent_logger.lifecycle(self.agent_name, "VERIFY", "wrap_model_call(sync) 진입")
        return handler(request)


# ======================================================================
# ForceToolUseMiddleware — MCP 도구 사용을 강제하는 미들웨어
# ======================================================================


class ForceToolUseMiddleware(AgentMiddleware):
    """에이전트가 도구를 한 번도 사용하지 않고 최종 답변하는 것을 방지하는 미들웨어.

    awrap_model_call 훅에서 모델 응답을 가로챈 뒤:
    1. tool_calls가 있으면 → 정상 통과
    2. 이전 대화에서 이미 도구를 사용한 적이 있으면 → 최종 답변 허용
    3. 도구 미사용 + 최종 답변 시도 → 강제 메시지 주입 후 재호출
    """

    _FORCE_MSG = (
        "반드시 제공된 도구(MCP tool)를 사용하여 자료를 검색한 후 답변하세요. "
        "자신의 사전 학습 지식만으로 답변하지 마세요. "
        "도구를 호출하세요."
    )

    def __init__(self, agent_name: str, max_retries: int = 1):
        super().__init__()
        self.agent_name = agent_name
        self._max_retries = max_retries

    @staticmethod
    def _has_tool_calls(response: ModelResponse) -> bool:
        """응답에 tool_calls가 포함되어 있는지 확인."""
        if not response.result:
            return False
        ai_msg = response.result[0]
        return bool(getattr(ai_msg, "tool_calls", None))

    @staticmethod
    def _history_has_tool_usage(messages: list) -> bool:
        """대화 히스토리에서 이전에 도구를 사용한 적이 있는지 확인."""
        return any(
            getattr(m, "tool_calls", None)
            for m in messages
            if isinstance(m, AIMessage)
        )

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler,
    ) -> ModelResponse:
        response = await handler(request)

        # tool_calls가 있으면 정상 통과
        if self._has_tool_calls(response):
            return response

        # 이전 대화에서 도구를 사용한 적이 있으면 최종 답변 허용
        if self._history_has_tool_usage(request.messages):
            return response

        # 도구 없이 바로 답변 → 재호출 시도
        for attempt in range(self._max_retries):
            agent_logger.lifecycle(
                self.agent_name,
                "FORCE_TOOL",
                f"도구 미사용 답변 감지, 재호출 시도 ({attempt + 1}/{self._max_retries})",
            )
            modified_request = request.override(
                messages=[*request.messages, HumanMessage(content=self._FORCE_MSG)],
            )
            response = await handler(modified_request)

            if self._has_tool_calls(response):
                agent_logger.lifecycle(
                    self.agent_name, "FORCE_TOOL", "재호출 후 도구 사용 확인"
                )
                return response

        # max_retries 초과 시 원본 응답 반환 (무한루프 방지)
        agent_logger.lifecycle(
            self.agent_name,
            "FORCE_TOOL",
            f"재시도 {self._max_retries}회 초과, 원본 응답 반환",
        )
        return response

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler,
    ) -> ModelResponse:
        """Sync fallback — 동기 환경에서는 통과."""
        return handler(request)