"""FastAPI application with SSE streaming for multi-agent workflow."""

import json
import time
import logging
import traceback
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage


from backend.schemas import ChatRequest, ReasoningStepData, MessageData, DataCard
from backend.agent import create_orchestrator
from backend.mcp_tools import mcp_manager
from backend.config import MAX_CONTEXT_TOKENS

logger = logging.getLogger(__name__)

# --- FastAPI App ---

app = FastAPI(
    title="DeepAgent Backend",
    description="Multi-agent workflow system with SSE streaming",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Create agent at startup (lazy, not at import time) ---

_orchestrator = None


@app.on_event("startup")
async def startup_event():
    """Initialize MCP connections and the orchestrator agent on startup."""
    global _orchestrator

    # Configure logging format once at startup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Initialize MCP server connections first so tools are available
    logger.info("Initializing MCP server connections...")
    await mcp_manager.initialize()

    logger.info("Initializing orchestrator agent...")
    _orchestrator = create_orchestrator()
    logger.info("Orchestrator agent ready.")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up MCP connections on shutdown."""
    await mcp_manager.shutdown()


# --- Helper functions ---

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sse_event(event: str, data) -> dict:
    """Format an SSE event dict for EventSourceResponse."""
    if isinstance(data, str):
        return {"event": event, "data": data}
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


# Agent display name mapping for user-friendly UI
_AGENT_DISPLAY: dict[str, tuple[str, str]] = {
    "research-agent": ("리서치 에이전트", "조사"),
    "report-writer-agent": ("리포트 작성 에이전트", "작성"),
}


def _extract_tool_display(
    tool_call: dict, reasoning_text: str = ""
) -> tuple[str, str]:
    """Extract a human-readable name and description from a tool call.

    Args:
        tool_call: The tool call dict from AIMessage.
        reasoning_text: Optional orchestrator reasoning text to use as
            a user-friendly description instead of raw args.

    Returns:
        (display_name, description)
    """
    name = tool_call.get("name", "unknown")
    args = tool_call.get("args", {})

    if name == "task":
        subagent_type = args.get("subagent_type", "agent")
        display_name, action_verb = _AGENT_DISPLAY.get(
            subagent_type, (subagent_type, "처리")
        )

        # Use orchestrator's reasoning text if available
        if reasoning_text:
            return display_name, reasoning_text

        # Fallback: generate friendly description from args
        desc = args.get("description", "")
        if desc:
            short_desc = desc[:80] + "..." if len(desc) > 80 else desc
            return display_name, f"{action_verb} 중: {short_desc}"

        return display_name, f"{action_verb}를 진행합니다"

    elif name == "duckduckgo_search":
        query = args.get("query", args.get("input", ""))
        return "웹 검색", f'"{query}" 검색 중'
    elif name == "write_todos":
        return "작업 계획", "작업 목록을 정리하고 있습니다"
    elif name in ("read_file", "write_file", "edit_file"):
        path = args.get("file_path", args.get("path", ""))
        return f"파일: {name}", f"{path}"
    elif name == "execute":
        cmd = args.get("command", "")
        return "명령 실행", f"실행 중: {cmd[:100]}" if cmd else "명령을 실행합니다"
    elif name in ("ls", "glob", "grep"):
        return f"검색: {name}", str(args)[:150]
    else:
        return name, str(args)[:150] if args else ""


def _extract_text_content(message: AIMessage) -> str:
    """Extract text from an AIMessage, handling both str and list content."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif isinstance(part, str):
                text_parts.append(part)
        return "\n".join(text_parts)
    return str(content)


def _try_extract_data_cards(text: str) -> list[dict]:
    """Attempt to extract data cards from structured text.

    Looks for patterns like "- Label: Value" or "**Label**: Value".
    """
    cards = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            line = line[2:]
        else:
            continue

        # Remove bold markers
        line = line.replace("**", "")

        if ": " in line:
            label, value = line.split(": ", 1)
            label = label.strip()
            value = value.strip()
            # Only short label + value pairs that look like data cards
            if 1 < len(label) < 50 and 0 < len(value) < 200:
                cards.append({"label": label, "value": value})

    return cards[:10]


def _extract_title(text: str) -> str:
    """Extract title from first markdown heading if present."""
    lines = text.strip().split("\n")
    if lines and lines[0].startswith("#"):
        return lines[0].lstrip("#").strip()
    return ""


def _extract_token_usage(msg: AIMessage, source: str = "unknown") -> dict | None:
    """Extract token usage from an AIMessage if available.

    Handles both OpenAI/vLLM style (response_metadata.token_usage)
    and LangChain standardized (usage_metadata).

    Args:
        msg: The AIMessage to extract usage from.
        source: Label identifying which agent produced this message
                (e.g. "orchestrator", "research-agent").
    """
    result = None

    # OpenAI/vLLM style via response_metadata
    rm = getattr(msg, "response_metadata", {}) or {}
    usage = rm.get("token_usage") or rm.get("usage")
    if usage and isinstance(usage, dict):
        result = {
            "promptTokens": usage.get("prompt_tokens", 0),
            "completionTokens": usage.get("completion_tokens", 0),
            "totalTokens": usage.get("total_tokens", 0),
            "maxContextTokens": MAX_CONTEXT_TOKENS,
            "source": source,
        }
    else:
        # LangChain standardized usage_metadata
        um = getattr(msg, "usage_metadata", None)
        if um:
            result = {
                "promptTokens": getattr(um, "input_tokens", 0),
                "completionTokens": getattr(um, "output_tokens", 0),
                "totalTokens": getattr(um, "total_tokens", 0),
                "maxContextTokens": MAX_CONTEXT_TOKENS,
                "source": source,
            }

    if result:
        logger.info(
            "Token usage [%s]: prompt=%d, completion=%d, total=%d (%.0f%% of %d)",
            source,
            result["promptTokens"],
            result["completionTokens"],
            result["totalTokens"],
            (result["promptTokens"] / MAX_CONTEXT_TOKENS * 100) if MAX_CONTEXT_TOKENS else 0,
            MAX_CONTEXT_TOKENS,
        )

    return result


# --- SSE Streaming Endpoint ---

async def _stream_agent_response(message: str, thread_id: str):
    """Stream agent response as SSE events.

    Uses dual stream_mode=["messages", "updates"]:
    - "messages" mode: real-time token-by-token streaming via AIMessageChunk
    - "updates" mode: structured node updates for tool calls and reasoning steps

    Event types emitted:
        - token: Real-time text token for streaming display
        - token_clear: Signal to clear streamed tokens (tool call detected)
        - reasoning_step: Tool calls, sub-agent invocations, intermediate steps
        - message: Final AI response with full content and metadata
        - metadata: Token usage information
        - error: Error information
        - done: Stream completion marker
    """
    start_time = time.monotonic()
    logger.info(
        "Orchestrator start processing — thread=%s, message_length=%d",
        thread_id,
        len(message),
    )

    try:
        config = {"configurable": {"thread_id": thread_id}}
        input_msg = {"messages": [{"role": "user", "content": message}]}

        # Track pending tool calls: tool_call_id -> display_name
        pending_tools: dict[str, str] = {}
        final_text = ""
        fallback_text = ""
        # Track token usage across the conversation for logging
        _prev_prompt_tokens = 0
        _max_prompt_tokens = 0
        # Token streaming state
        _streamed_any = False

        async for event in _orchestrator.astream(
            input_msg,
            config=config,
            stream_mode=["messages", "updates"],
        ):
            mode = event[0]
            chunk = event[1]

            # ── messages mode: real-time token streaming ──────────
            if mode == "messages":
                msg, _metadata = chunk

                if isinstance(msg, AIMessageChunk):
                    # Check for tool call chunks
                    tool_chunks = getattr(msg, "tool_call_chunks", None) or []
                    has_tool_chunks = bool(tool_chunks) and any(
                        tc.get("name") or tc.get("args") for tc in tool_chunks
                    )

                    if has_tool_chunks:
                        # Tool call detected — clear any streamed tokens
                        if _streamed_any:
                            yield _sse_event("token_clear", {})
                            _streamed_any = False
                    else:
                        # Extract text content from chunk
                        text = ""
                        content = msg.content
                        if isinstance(content, str):
                            text = content
                        elif isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    text += part.get("text", "")
                                elif isinstance(part, str):
                                    text += part

                        if text:
                            yield _sse_event("token", {"content": text})
                            _streamed_any = True

                continue  # Skip updates processing for messages chunks

            # ── updates mode: structured node events ──────────────
            if not isinstance(chunk, dict):
                continue

            for node_name, update in chunk.items():
                if not isinstance(update, dict):
                    continue

                messages = update.get("messages", [])
                if not isinstance(messages, list):
                    messages = [messages]

                for msg in messages:
                    # --- AIMessage with tool_calls: emit reasoning steps ---
                    if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                        reasoning_text = _extract_text_content(msg).strip()

                        for tc in msg.tool_calls:
                            tc_id = tc.get("id", "")
                            display_name, description = _extract_tool_display(
                                tc, reasoning_text
                            )
                            pending_tools[tc_id] = display_name

                            tc_name = tc.get("name", "unknown")
                            tc_args_str = str(tc.get("args", {}))
                            logger.info(
                                "Tool call: name=%s, args=%s",
                                tc_name,
                                tc_args_str[:200],
                            )
                            if tc_name == "task":
                                subagent_type = tc.get("args", {}).get(
                                    "subagent_type", "unknown"
                                )
                                task_desc = tc.get("args", {}).get(
                                    "description", ""
                                )
                                logger.info(
                                    "Sub-agent invocation: agent=%s, task=%s",
                                    subagent_type,
                                    task_desc[:150],
                                )

                            logger.debug(
                                "Emitting reasoning_step: name=%s, status=in_progress",
                                display_name,
                            )
                            yield _sse_event("reasoning_step", {
                                "name": display_name,
                                "status": "in_progress",
                                "description": description,
                                "timestamp": _now_iso(),
                            })

                        if reasoning_text:
                            fallback_text = reasoning_text

                        # Emit token usage metadata if available
                        token_usage = _extract_token_usage(msg, source=node_name)
                        if token_usage:
                            pt = token_usage["promptTokens"]
                            if pt != _prev_prompt_tokens:
                                delta = pt - _prev_prompt_tokens
                                logger.info(
                                    "Context change [%s]: %d → %d (%+d tokens)",
                                    node_name, _prev_prompt_tokens, pt, delta,
                                )
                                _prev_prompt_tokens = pt
                            _max_prompt_tokens = max(_max_prompt_tokens, pt)
                            yield _sse_event("metadata", token_usage)

                    # --- ToolMessage: mark tool as completed ---
                    elif isinstance(msg, ToolMessage):
                        tc_id = getattr(msg, "tool_call_id", "")
                        tool_name = getattr(msg, "name", "")
                        display_name = pending_tools.pop(tc_id, tool_name or "Tool")

                        content_str = str(msg.content) if msg.content else ""
                        preview = content_str[:200]

                        logger.info(
                            "Sub-agent/tool completed: name=%s, result_length=%d",
                            display_name,
                            len(content_str),
                        )
                        logger.debug(
                            "Emitting reasoning_step: name=%s, status=completed",
                            display_name,
                        )
                        yield _sse_event("reasoning_step", {
                            "name": display_name,
                            "status": "completed",
                            "description": preview,
                            "timestamp": _now_iso(),
                        })

                    # --- AIMessage without tool_calls: final response ---
                    elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                        text = _extract_text_content(msg)
                        if text.strip():
                            final_text = text
                            logger.debug(
                                "Captured final AIMessage text (length=%d)",
                                len(text),
                            )

                        # Emit token usage metadata if available
                        token_usage = _extract_token_usage(msg, source=node_name)
                        if token_usage:
                            pt = token_usage["promptTokens"]
                            if pt != _prev_prompt_tokens:
                                delta = pt - _prev_prompt_tokens
                                logger.info(
                                    "Context change [%s]: %d → %d (%+d tokens)",
                                    node_name, _prev_prompt_tokens, pt, delta,
                                )
                                _prev_prompt_tokens = pt
                            _max_prompt_tokens = max(_max_prompt_tokens, pt)
                            yield _sse_event("metadata", token_usage)

        # Emit final message
        elapsed = time.monotonic() - start_time

        # If no clean final text, fall back to intermediate orchestrator text
        if not final_text.strip() and fallback_text.strip():
            logger.info(
                "No final AIMessage text; using fallback_text (length=%d)",
                len(fallback_text),
            )
            final_text = fallback_text

        if final_text.strip():
            data_cards = _try_extract_data_cards(final_text)
            title = _extract_title(final_text)

            source = "orchestrator"
            if final_text is fallback_text:
                source = "orchestrator (partial)"

            logger.info(
                "Emitting message event — source=%s, length=%d, elapsed=%.1fs",
                source,
                len(final_text),
                elapsed,
            )
            yield _sse_event("message", {
                "role": "assistant",
                "content": final_text,
                "title": title,
                "dataCards": data_cards,
                "source": source,
                "processingTime": f"{elapsed:.1f}s",
            })
        else:
            logger.warning(
                "Stream completed with no final text after %.1fs", elapsed
            )

    except Exception as e:
        elapsed = time.monotonic() - start_time
        logger.error("Agent streaming error after %.1fs: %s", elapsed, traceback.format_exc())

        # If we captured intermediate content, emit it before the error
        # so the user sees partial results.
        if fallback_text.strip() and not final_text.strip():
            logger.info(
                "Emitting fallback message before error (length=%d)",
                len(fallback_text),
            )
            yield _sse_event("message", {
                "role": "assistant",
                "content": fallback_text,
                "title": _extract_title(fallback_text),
                "dataCards": _try_extract_data_cards(fallback_text),
                "source": "orchestrator (partial)",
                "processingTime": f"{elapsed:.1f}s",
            })

        logger.info("Emitting error event — type=%s", type(e).__name__)
        yield _sse_event("error", {
            "error": str(e),
            "type": type(e).__name__,
        })

    finally:
        elapsed = time.monotonic() - start_time
        logger.info(
            "Emitting done event — thread=%s, total_elapsed=%.1fs",
            thread_id,
            elapsed,
        )
        if _max_prompt_tokens > 0:
            usage_pct = _max_prompt_tokens / MAX_CONTEXT_TOKENS * 100
            logger.info(
                "Context summary — peak_prompt_tokens=%d (%.0f%% of %d), "
                "final_prompt_tokens=%d",
                _max_prompt_tokens,
                usage_pct,
                MAX_CONTEXT_TOKENS,
                _prev_prompt_tokens,
            )
            if usage_pct > 80:
                logger.warning(
                    "Context usage HIGH (%.0f%%) — consider conversation "
                    "history trimming for thread=%s",
                    usage_pct,
                    thread_id,
                )
        yield _sse_event("done", json.dumps({"status": "completed"}))


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """SSE streaming chat endpoint.

    Accepts a user message and thread_id, returns an SSE stream of:
    - reasoning_step events (tool calls, sub-agent work)
    - message events (final AI responses)
    - done event (stream completion)
    """
    return EventSourceResponse(
        _stream_agent_response(request.message, request.thread_id),
        media_type="text/event-stream",
    )


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "agent_ready": _orchestrator is not None,
        "service": "deepagent-backend",
        "timestamp": _now_iso(),
    }


# --- MCP Health Check ---

@app.get("/api/mcp/health")
async def mcp_health():
    """Check health of all configured MCP servers."""
    servers = await mcp_manager.check_health()
    online = sum(1 for s in servers if s["status"] == "online")
    total_enabled = sum(1 for s in servers if s["enabled"])
    return {
        "summary": {"online": online, "total_enabled": total_enabled, "total": len(servers)},
        "servers": servers,
        "timestamp": _now_iso(),
    }


@app.get("/mcp/dashboard", response_class=HTMLResponse)
async def mcp_dashboard():
    """MCP server health check dashboard."""
    return _MCP_DASHBOARD_HTML


_MCP_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MCP Health Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f1117; color: #e0e0e0; padding: 2rem; }
  h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
  .subtitle { color: #888; font-size: 0.85rem; margin-bottom: 1.5rem; }
  .summary { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
  .summary-card { background: #1a1d27; border-radius: 8px; padding: 1rem 1.5rem;
                  flex: 1; text-align: center; }
  .summary-card .num { font-size: 2rem; font-weight: 700; }
  .summary-card .label { font-size: 0.75rem; color: #888; margin-top: 0.25rem; }
  .online .num { color: #4ade80; }
  .offline .num { color: #f87171; }
  .total .num { color: #60a5fa; }
  table { width: 100%; border-collapse: collapse; background: #1a1d27;
          border-radius: 8px; overflow: hidden; }
  th { background: #252833; text-align: left; padding: 0.75rem 1rem;
       font-size: 0.75rem; text-transform: uppercase; color: #888; }
  td { padding: 0.75rem 1rem; border-top: 1px solid #252833; font-size: 0.875rem; }
  .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px;
           font-size: 0.75rem; font-weight: 600; }
  .badge-online { background: #064e3b; color: #4ade80; }
  .badge-reachable { background: #1e3a5f; color: #60a5fa; }
  .badge-offline { background: #4c1d1d; color: #f87171; }
  .badge-error { background: #4c1d1d; color: #f87171; }
  .badge-disabled { background: #333; color: #666; }
  .tools-list { display: flex; flex-wrap: wrap; gap: 0.3rem; }
  .tool-chip { background: #252833; padding: 0.15rem 0.5rem; border-radius: 4px;
               font-size: 0.75rem; color: #a5b4fc; }
  .latency { color: #888; font-size: 0.8rem; }
  .error-msg { color: #f87171; font-size: 0.8rem; }
  .refresh-bar { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
  .btn { background: #252833; border: 1px solid #333; color: #e0e0e0;
         padding: 0.4rem 1rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; }
  .btn:hover { background: #333; }
  .auto-label { font-size: 0.8rem; color: #888; }
  .spinner { display: none; width: 16px; height: 16px; border: 2px solid #333;
             border-top-color: #60a5fa; border-radius: 50%; animation: spin 0.6s linear infinite; }
  .spinner.active { display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
  <h1>MCP Health Dashboard</h1>
  <p class="subtitle">DeepAgent-Base MCP Server Monitor</p>

  <div class="summary">
    <div class="summary-card online"><div class="num" id="s-online">-</div><div class="label">Online</div></div>
    <div class="summary-card offline"><div class="num" id="s-offline">-</div><div class="label">Offline</div></div>
    <div class="summary-card total"><div class="num" id="s-total">-</div><div class="label">Total</div></div>
  </div>

  <div class="refresh-bar">
    <button class="btn" onclick="fetchHealth()">Refresh</button>
    <div class="spinner" id="spinner"></div>
    <label class="auto-label">
      <input type="checkbox" id="auto-refresh" checked> Auto-refresh (10s)
    </label>
    <span class="auto-label" id="last-update"></span>
  </div>

  <table>
    <thead>
      <tr><th>Name</th><th>Status</th><th>Transport</th><th>URL</th><th>Latency</th><th>Tools</th><th>Error</th></tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>

<script>
let timer = null;

async function fetchHealth() {
  const spinner = document.getElementById('spinner');
  spinner.classList.add('active');
  try {
    const res = await fetch('/api/mcp/health');
    const data = await res.json();
    render(data);
  } catch (e) {
    document.getElementById('tbody').innerHTML =
      '<tr><td colspan="7" style="color:#f87171">Failed to fetch: ' + e.message + '</td></tr>';
  } finally {
    spinner.classList.remove('active');
  }
}

function render(data) {
  const { summary, servers, timestamp } = data;
  document.getElementById('s-online').textContent = summary.online;
  document.getElementById('s-offline').textContent = summary.total_enabled - summary.online;
  document.getElementById('s-total').textContent = summary.total;
  document.getElementById('last-update').textContent = 'Updated: ' + new Date(timestamp).toLocaleTimeString();

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = servers.map(s => {
    const badgeCls = 'badge-' + s.status;
    const tools = (s.tools || []).map(t => '<span class="tool-chip" title="'+esc(t.description)+'">'+esc(t.name)+'</span>').join('');
    return '<tr>' +
      '<td><strong>'+esc(s.name)+'</strong><br><span style="color:#888;font-size:0.75rem">'+esc(s.description)+'</span></td>' +
      '<td><span class="badge '+badgeCls+'">'+s.status+'</span></td>' +
      '<td>'+esc(s.transport)+'</td>' +
      '<td style="font-size:0.8rem;color:#888">'+esc(s.url)+'</td>' +
      '<td class="latency">'+(s.latency_ms != null ? s.latency_ms + ' ms' : '-')+'</td>' +
      '<td><div class="tools-list">'+(tools || '-')+'</div></td>' +
      '<td class="error-msg">'+(s.error ? esc(s.error) : '-')+'</td>' +
      '</tr>';
  }).join('');
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

function scheduleRefresh() {
  clearInterval(timer);
  if (document.getElementById('auto-refresh').checked) {
    timer = setInterval(fetchHealth, 10000);
  }
}

document.getElementById('auto-refresh').addEventListener('change', scheduleRefresh);
fetchHealth();
scheduleRefresh();
</script>
</body>
</html>
"""
