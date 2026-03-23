"""Agent workflow using deepagents with orchestrator + sub-agents."""

import logging
from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from backend.config import get_model, AGENT_ROOT_DIR, AGENTS_MD_PATH, SKILLS_DIR
from backend.mcp_tools import mcp_manager
from backend.prompts import *
from backend import agent_logger
from backend.callback_handler import TracingMiddleware, LawVerificationMiddleware, ForceToolUseMiddleware
from langchain.agents.middleware import ToolCallLimitMiddleware
from deepagents.middleware import create_summarization_tool_middleware



logger = logging.getLogger(__name__)

# Summarization 미들웨어 DEBUG 로그 활성화

logging.getLogger("deepagents.middleware.summarization").setLevel(logging.DEBUG)
logging.getLogger("deepagents.middleware.filesystem").setLevel(logging.DEBUG)  # 파일 조작 로그
logging.getLogger("deepagents.backend").setLevel(logging.DEBUG)              # 백엔드 저장 로그

# --- System Prompts ---


# --- Sub-Agent Definitions ---


# Use a lower max_tokens for sub-agents so their responses don't blow
# the orchestrator's 32768-token context window on the next vLLM call.
_subagent_model = get_model("openai")
mini_model = get_model("openai_mini")

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
    "backend" : FilesystemBackend(root_dir=AGENT_ROOT_DIR, virtual_mode=True),
    "middleware": [
                TracingMiddleware("research-agent"),
                # ForceToolUseMiddleware("research-agent", max_retries=1),
                ToolCallLimitMiddleware(  # 특정 tool 제한: 해당 tool만 스레드당 10회, run당 5회
                            tool_name="hug-rag",
                            thread_limit=10,
                            run_limit=5,
                        ),
                create_summarization_tool_middleware(mini_model, StateBackend)]
                    
    
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
    "backend" : FilesystemBackend(root_dir=AGENT_ROOT_DIR, virtual_mode=True),
    "middleware": [TracingMiddleware("risk-assessment-agent"),
                #    ForceToolUseMiddleware("risk-assessment-agent", max_retries=1),
                   LawVerificationMiddleware(),
                   ToolCallLimitMiddleware(  # 특정 tool 제한: 해당 tool만 스레드당 10회, run당 5회
                            tool_name="hug-rag",
                            thread_limit=10,
                            run_limit=5,
                        ),
                    create_summarization_tool_middleware(mini_model, StateBackend)]
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
    messages: Annotated[list[BaseMessage], add_messages]


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
    workflow = StateGraph(WorkflowState)

    workflow.add_node(
        "orchestrator",
        inner_agent,
        retry_policy=RetryPolicy(
            max_attempts=2,
            initial_interval=1.0,
            retry_on=lambda e: isinstance(e, (TimeoutError, ConnectionError, OSError)),
        ),
    )

    workflow.add_edge(START, "orchestrator")
    workflow.add_edge("orchestrator", END)

    return workflow.compile(checkpointer=checkpointer)


def create_orchestrator():
    """Create the orchestrator agent with sub-agents.

    Must be called *after* ``mcp_manager.initialize()`` so that any enabled
    MCP tools are available to the research agent.
    """
    
    model = get_model("openai")
    agent_logger.lifecycle(
        "orchestrator", "INIT", f"Creating orchestrator {model.__dict__}"
    )

    # Startup sync: rebuild tools to include any MCP tools loaded after module init
    research_agent_spec["tools"] = _build_research_tools()
    risk_assessment_agent_spec["tools"] = _build_risk_assessment_tools()

    # Inject MCP tool descriptions into both orchestrator and research-agent prompts
    mcp_desc = _build_mcp_tools_description()
    system_prompt = ORCHESTRATOR_PROMPT + mcp_desc

    if mcp_desc:
        logger.info("Injected MCP tool descriptions into orchestrator prompt")

    subagent_names = [
        s["name"] for s in [research_agent_spec, risk_assessment_agent_spec]
    ]
    agent_logger.lifecycle(
        "orchestrator",
        "AGENTS",
        f"Sub-agents: {subagent_names}",
    )

    

    inner_agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        subagents=[research_agent_spec, risk_assessment_agent_spec],
        memory=[AGENTS_MD_PATH],
        backend=FilesystemBackend(root_dir=AGENT_ROOT_DIR, virtual_mode=True),
        name="orchestrator",
        skills=[SKILLS_DIR],
    )
    agent_logger.lifecycle(
        "orchestrator", "READY", "Inner agent created, wrapping with LangGraph workflow"
    )
    return _build_workflow_graph(inner_agent)
