"""Agent workflow using deepagents with orchestrator + sub-agents."""

import logging

from langchain_community.tools import DuckDuckGoSearchRun
from langgraph.checkpoint.memory import MemorySaver

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from backend.config import get_model, AGENT_ROOT_DIR, AGENTS_MD_PATH, SKILLS_DIR
from backend.mcp_tools import mcp_manager
from backend.prompts import *

logger = logging.getLogger(__name__)


# --- System Prompts ---




# --- Sub-Agent Definitions ---

search_tool = DuckDuckGoSearchRun()

# Use a lower max_tokens for sub-agents so their responses don't blow
# the orchestrator's 32768-token context window on the next vLLM call.
_subagent_model = get_model(max_tokens=2048)

def _build_research_tools() -> list:
    """Build the tool list for the research agent (DuckDuckGo + any MCP tools)."""
    tools = [search_tool]
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
    "tools": _build_research_tools(),  # DuckDuckGo + MCP tools (if loaded)
    "model": _subagent_model,
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
}

report_writer_spec = {
    "name": "report-writer-agent",
    "description": (
        "Report writer agent for creating structured, professional reports. "
        "Delegate to this agent when you need to write a report, summary, or "
        "structured document from gathered information. Provide all the research "
        "data and context it needs to write the report."
    ),
    "system_prompt": REPORT_WRITER_PROMPT,
    "model": _subagent_model,
}


# --- Checkpointer for conversation memory ---

checkpointer = MemorySaver()


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


def create_orchestrator():
    """Create the orchestrator agent with sub-agents.

    Must be called *after* ``mcp_manager.initialize()`` so that any enabled
    MCP tools are available to the research agent.
    """
    logger.info("Creating orchestrator agent (model max_tokens=4096)")
    model = get_model()

    # Startup sync: rebuild tools to include any MCP tools loaded after module init
    research_agent_spec["tools"] = _build_research_tools()
    risk_assessment_agent_spec["tools"] = _build_risk_assessment_tools()

    # Inject MCP tool descriptions into both orchestrator and research-agent prompts
    mcp_desc = _build_mcp_tools_description()
    system_prompt = ORCHESTRATOR_PROMPT + mcp_desc

    mcp_tools = mcp_manager.get_tools()
    if mcp_tools:
        tool_lines = []
        for tool in mcp_tools:
            name = tool.name
            desc = (tool.description or "").strip().split("\n")[0]
            tool_lines.append(f"- **{name}**: {desc}")
        mcp_tool_section = (
            "\n## Available MCP Tools\n"
            + "아래 MCP 도구를 우선적으로 사용하세요. DuckDuckGo보다 더 정확한 결과를 제공합니다.\n\n"
            + "\n".join(tool_lines)
            + "\n"
        )
        research_agent_spec["system_prompt"] = RESEARCH_AGENT_PROMPT + mcp_tool_section

        # hug-rag 도구 설명만 risk-assessment-agent에 주입
        hug_tool_lines = [l for l in tool_lines if "hug" in l.lower()]
        if hug_tool_lines:
            risk_assessment_agent_spec["system_prompt"] = (
                RISK_ASSESSMENT_AGENT_PROMPT
                + "\n## Available MCP Tools\n"
                + "아래 MCP 도구를 사용하여 전세 관련 법령 및 가이드를 검색하세요.\n\n"
                + "\n".join(hug_tool_lines)
                + "\n"
            )
    if mcp_desc:
        logger.info("Injected MCP tool descriptions into orchestrator prompt")

    subagent_names = [s["name"] for s in [research_agent_spec, report_writer_spec, risk_assessment_agent_spec]]
    logger.info(
        "Registering sub-agents: %s (model max_tokens=2048)", subagent_names
    )

    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        subagents=[research_agent_spec, report_writer_spec, risk_assessment_agent_spec],
        memory=[AGENTS_MD_PATH],
        backend=FilesystemBackend(root_dir=AGENT_ROOT_DIR),
        checkpointer=checkpointer,
        name="orchestrator",
        skills=[SKILLS_DIR],
    )
    logger.info("Orchestrator agent created successfully")
    return agent
