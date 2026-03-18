"""Agent workflow using deepagents with orchestrator + sub-agents."""

import logging
from typing import Annotated, Literal
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from backend.config import get_model, AGENT_ROOT_DIR, AGENTS_MD_PATH, SKILLS_DIR
from backend.mcp_tools import mcp_manager
from backend.prompts import *
from backend import agent_logger
from backend.callback_handler import AgentTraceCallbackHandler, TracingMiddleware

logger = logging.getLogger(__name__)


# --- System Prompts ---




# --- Sub-Agent Definitions ---


# Use a lower max_tokens for sub-agents so their responses don't blow
# the orchestrator's 32768-token context window on the next vLLM call.
_subagent_model = get_model(max_tokens=2048)

def _build_research_tools() -> list:
    """Build the tool list for the research agent (any MCP tools)."""
    tools = []
    mcp_tools = mcp_manager.get_tools()
    if mcp_tools:
        logger.info("Adding %d MCP tool(s) to research agent", len(mcp_tools))
        tools.extend(mcp_tools)
    return tools


research_agent_spec = {
    "name": "research-agent",
    "description": (
        "Research agent for investigating topics using web search. "
        "Delegate to this agent when you need to gather information, "
        "look up facts, or research a topic. Give it one focused topic at a time."
    ),
    "system_prompt": RESEARCH_AGENT_PROMPT,
    "tools": _build_research_tools(),  # MCP tools (if loaded)
    "model": _subagent_model,
    "middleware": [TracingMiddleware("research-agent")],
}

def _build_risk_assessment_tools() -> list:
    """Build the tool list for the risk assessment agent (MCP tools only)."""
    mcp_tools = mcp_manager.get_tools()
    return [t for t in mcp_tools if "hug" in t.name.lower()] if mcp_tools else []


risk_assessment_agent_spec = {
    "name": "risk-assessment-agent",
    "description": (
        "전세계약 조항에 대한 위험도를 분석하는 에이전트입니다. "
        "Delegate to this agent when you need to assess the risks of a contract clause. "
        "Give it one focused contract clause at a time."
    ),
    "system_prompt": RISK_ASSESSMENT_AGENT_PROMPT,
    "tools": _build_risk_assessment_tools(),
    "model": _subagent_model,
    "middleware": [TracingMiddleware("risk-assessment-agent")],
}

# report_writer_spec = {
#     "name": "report-writer-agent",
#     "description": (
#         "Report writer agent for creating structured, professional reports. "
#         "Delegate to this agent when you need to write a report, summary, or "
#         "structured document from gathered information. Provide all the research "
#         "data and context it needs to write the report."
#     ),
#     "system_prompt": REPORT_WRITER_PROMPT,
#     "model": _subagent_model,
#     "middleware": [TracingMiddleware("report-writer-agent")],
# }


# --- Checkpointer for conversation memory ---

checkpointer = MemorySaver()


# --- LangGraph Workflow State ---

class WorkflowState(TypedDict):
    """State for the LangGraph workflow wrapper.

    Uses add_messages reducer to accumulate messages instead of overwriting.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    retry_count: int
    last_error: str
    fallback_used: bool


# --- Create the orchestrator agent ---

def _build_mcp_tools_description() -> str:
    """Build a description of available MCP tools for the orchestrator prompt."""
    mcp_tools = mcp_manager.get_tools()
    if not mcp_tools:
        return ""

    lines = [
        "\n## Available MCP Tools",
        "The research-agent has access to the following MCP tools in addition to web search.",
        "When a user request matches an MCP tool's capability, instruct the research-agent to use it.\n",
    ]
    for tool in mcp_tools:
        name = tool.name
        desc = (tool.description or "").strip().split("\n")[0]
        lines.append(f"- **{name}**: {desc}")

    return "\n".join(lines)


def _build_workflow_graph(inner_agent: CompiledStateGraph) -> CompiledStateGraph:
    """Wrap the deepagents orchestrator in a LangGraph StateGraph with retry and fallback.

    The wrapper graph adds:
    - RetryPolicy for transient errors (network, timeout)
    - Conditional routing for business-level failures
    - Fallback node using research agent directly

    Args:
        inner_agent: The deepagents orchestrator CompiledStateGraph.

    Returns:
        A compiled workflow graph with retry/fallback capabilities.
    """

    # Shared callback handler for real-time logging during ainvoke()
    _trace_handler = AgentTraceCallbackHandler(agent_name="orchestrator")

    async def orchestrator_node(state: WorkflowState) -> dict:
        """Call the deepagents orchestrator, filtering state to compatible keys."""
        agent_input = {"messages": state["messages"]}
        try:
            result = await inner_agent.ainvoke(
                agent_input,
                config={"callbacks": [_trace_handler]},
            )
            return {
                "messages": result["messages"],
                "retry_count": 0,
                "last_error": "",
            }
        except Exception as e:
            retry = state.get("retry_count", 0) + 1
            agent_logger.error("orchestrator", f"{e} (retry {retry})")
            return {
                "messages": [AIMessage(content=f"처리 중 오류가 발생했습니다: {e}")],
                "retry_count": retry,
                "last_error": str(e),
            }

    _fallback_trace_handler = AgentTraceCallbackHandler(agent_name="fallback")

    async def fallback_node(state: WorkflowState) -> dict:
        """Fallback: call research agent directly when orchestrator fails."""
        agent_logger.lifecycle("fallback", "START", "Orchestrator failed, using fallback research agent")
        try:
            fallback_agent = create_deep_agent(
                model=get_model(max_tokens=2048),
                tools=_build_research_tools(),
                system_prompt=RESEARCH_AGENT_PROMPT,
                name="fallback-research",
            )
            agent_input = {"messages": state["messages"]}
            result = await fallback_agent.ainvoke(
                agent_input,
                config={"callbacks": [_fallback_trace_handler]},
            )
            return {
                "messages": result["messages"],
                "fallback_used": True,
                "last_error": "",
            }
        except Exception as e:
            agent_logger.error("fallback", str(e))
            return {
                "messages": [AIMessage(content=f"Fallback 처리도 실패했습니다: {e}")],
                "last_error": str(e),
            }

    def route_after_orchestrator(
        state: WorkflowState,
    ) -> Literal["end", "fallback", "retry"]:
        """Route based on error state: success -> end, retryable -> retry, exhausted -> fallback."""
        last_error = state.get("last_error", "")
        retry_count = state.get("retry_count", 0)

        if not last_error:
            return "end"
        if retry_count <= 2:
            return "retry"
        return "fallback"

    workflow = StateGraph(WorkflowState)

    workflow.add_node(
        "orchestrator",
        orchestrator_node,
        retry_policy=RetryPolicy(
            max_attempts=2,
            initial_interval=1.0,
            retry_on=lambda e: isinstance(e, (TimeoutError, ConnectionError, OSError)),
        ),
    )
    workflow.add_node("fallback", fallback_node)

    workflow.add_edge(START, "orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {"end": END, "fallback": "fallback", "retry": "orchestrator"},
    )
    workflow.add_edge("fallback", END)

    return workflow.compile(checkpointer=checkpointer)


def create_orchestrator():
    """Create the orchestrator agent with sub-agents.

    Must be called *after* ``mcp_manager.initialize()`` so that any enabled
    MCP tools are available to the research agent.
    """
    agent_logger.lifecycle("orchestrator", "INIT", "Creating orchestrator (max_tokens=4096)")
    model = get_model()

    # Startup sync: rebuild tools to include any MCP tools loaded after module init
    research_agent_spec["tools"] = _build_research_tools()
    risk_assessment_agent_spec["tools"] = _build_risk_assessment_tools()

    # Inject MCP tool descriptions into both orchestrator and research-agent prompts
    mcp_desc = _build_mcp_tools_description()
    system_prompt = ORCHESTRATOR_PROMPT + mcp_desc
    

    
        
    if mcp_desc:
        logger.info("Injected MCP tool descriptions into orchestrator prompt")

    subagent_names = [s["name"] for s in [research_agent_spec, risk_assessment_agent_spec]]
    agent_logger.lifecycle(
        "orchestrator", "AGENTS",
        f"Sub-agents: {subagent_names}",
    )
    
    # 추후 ToolCallLimitMiddleware 추가 고려
    inner_agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        subagents=[research_agent_spec, risk_assessment_agent_spec],
        memory=[AGENTS_MD_PATH],
        backend=FilesystemBackend(root_dir=AGENT_ROOT_DIR),
        name="orchestrator",
        skills=[SKILLS_DIR],
    )
    agent_logger.lifecycle("orchestrator", "READY", "Inner agent created, wrapping with LangGraph workflow")
    return _build_workflow_graph(inner_agent)
