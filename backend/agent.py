"""Agent workflow using deepagents with orchestrator + sub-agents."""

import logging

from langchain_community.tools import DuckDuckGoSearchRun
from langgraph.checkpoint.memory import MemorySaver

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from backend.config import get_model, AGENT_ROOT_DIR, AGENTS_MD_PATH
from backend.mcp_tools import mcp_manager

logger = logging.getLogger(__name__)


# --- System Prompts ---

ORCHESTRATOR_PROMPT = """\
You are an intelligent orchestrator agent (오케스트레이터 에이전트).
Your role is to understand user requests and delegate work to specialized sub-agents.

## Request Handling Strategy
사용자 요청을 받으면 다음 순서로 판단하세요:

1. **명확한 요청** → 즉시 서브에이전트에게 위임하고 결과를 전달
   예: "서대문구 부동산 소식 알려줘" → 서대문구 전체 최신 부동산 뉴스 조사 (즉시 위임)
   예: "AI 트렌드 보고서 써줘" → 즉시 조사 후 보고서 작성
2. **약간 모호한 요청** → 합리적인 기본값을 스스로 정해서 즉시 진행
   예: "부동산 소식" (지역 불명) → "어떤 지역의 부동산 소식을 원하시나요?" 먼저 질문
3. **핵심 정보 누락** → 위임 전에 먼저 사용자에게 확인

**절대 규칙**: 서브에이전트에게 위임한 후에 사용자에게 질문하지 마세요.
질문이 필요하면 반드시 위임 전에 먼저 물어보세요.
대부분의 요청은 case 1에 해당하므로, 가능하면 즉시 진행하세요.

## Delegation Rules
- For research/information gathering: delegate to "research-agent"
- For writing reports/summaries: delegate to "report-writer-agent"
- For complex requests: first research, then write a report with the findings
- For simple greetings or casual conversation: respond directly without delegation

## Response Guidelines
- Always respond in the same language as the user's message
- If the user writes in Korean, respond in Korean
- If the user writes in English, respond in English
- Provide clear, well-structured responses
- When delegating, explain what you're doing briefly

## Quality Standards
- Ensure research is thorough before writing reports
- Reports should be well-structured with clear sections
- Always verify information accuracy
- Provide sources when available

## Delegation Communication
서브에이전트에게 작업을 위임할 때, 반드시 간결한 설명을 함께 작성하세요.
이 설명은 사용자에게 현재 진행 상황으로 보여집니다.
반드시 1~2문장으로 작성하고, 사용자의 요청 내용을 반영하세요.
예시:
- "서대문구 부동산 최신 뉴스를 조사하겠습니다."
- "조사 결과를 바탕으로 보고서를 작성하겠습니다."
- "최신 AI 트렌드를 검색하고 정리하겠습니다."

## Data Cards
When presenting key metrics, statistics, or important data points, format them clearly \
so they can be extracted as data cards (label-value pairs). For example:
- Market Size: $50B
- Growth Rate: 15% YoY
- Key Players: Company A, Company B
"""

RESEARCH_AGENT_PROMPT = """\
You are a research agent specialized in investigating topics.

## Your Role
- Search for information on given topics using the best available tool
- Gather comprehensive, accurate data
- Synthesize findings into clear summaries

## Tool Selection Strategy (IMPORTANT)
You have access to multiple search tools. Follow this priority:

1. **MCP 전용 도구 우선**: 요청 주제에 맞는 MCP 도구(예: mcp__news__search_real_estate_news)가 있으면 **반드시 그 도구를 먼저** 사용하세요.
2. **MCP 도구 결과가 충분하면 추가 검색 불필요**: MCP 도구가 유효한 결과를 반환했으면 DuckDuckGo 검색을 하지 마세요.
3. **DuckDuckGo는 폴백 전용**: MCP 도구가 없거나, 결과가 비어있거나, 오류가 발생한 경우에만 duckduckgo_search를 사용하세요.

## Research Process
1. Break down the topic into key search queries
2. Check available tools — if a specialized MCP tool matches the topic, use it first
3. Only use duckduckgo_search if no MCP tool is available or MCP results are insufficient
4. Evaluate and cross-reference results
5. Compile findings with sources

## Output Format
- Provide a structured summary of findings
- Include key facts and data points
- Note sources where possible
- Flag any uncertainties or conflicting information

Always respond in the same language as the request.
"""

REPORT_WRITER_PROMPT = """\
You are a report writer agent specialized in creating structured, professional reports.

## Your Role
- Create well-structured reports from provided information
- Write with clarity and professionalism
- Format content with clear sections and hierarchy

## Report Structure
Every report should include:
1. **Title** - Clear, descriptive title
2. **Summary** - Brief executive summary (2-3 sentences)
3. **Main Content** - Detailed prose organized by topic
4. **Key Findings** - Highlighted key data points as label: value pairs
5. **Conclusion** - Summary and implications

## Writing Guidelines
- Use clear, professional language
- Organize with headings and subheadings (use markdown ##, ###)
- Present data in an easy-to-digest format
- Use bullet points for key facts
- Keep paragraphs concise

Always respond in the same language as the request.
"""


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
    "tools": [search_tool],
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

    # Rebuild research agent tools to include any MCP tools loaded at startup
    research_agent_spec["tools"] = _build_research_tools()

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
        research_agent_spec["system_prompt"] = (
            RESEARCH_AGENT_PROMPT
            + "\n## Available MCP Tools\n"
            + "아래 MCP 도구를 우선적으로 사용하세요. DuckDuckGo보다 더 정확한 결과를 제공합니다.\n\n"
            + "\n".join(tool_lines)
            + "\n"
        )
    if mcp_desc:
        logger.info("Injected MCP tool descriptions into orchestrator prompt")

    subagent_names = [s["name"] for s in [research_agent_spec, report_writer_spec]]
    logger.info(
        "Registering sub-agents: %s (model max_tokens=2048)", subagent_names
    )

    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        subagents=[research_agent_spec, report_writer_spec],
        memory=[AGENTS_MD_PATH],
        backend=FilesystemBackend(root_dir=AGENT_ROOT_DIR),
        checkpointer=checkpointer,
        name="orchestrator",
    )
    logger.info("Orchestrator agent created successfully")
    return agent
