"""MCP server template - 새 MCP 도구를 만들 때 이 파일을 복사하세요."""

import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "tool-name",  # TODO: 도구 이름으로 변경
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8001")),
)


@mcp.tool()
def example_tool(query: str) -> dict:
    """
    도구 설명을 여기에 작성합니다.

    Args:
        query: 입력 파라미터 설명

    Returns:
        결과 딕셔너리
    """
    # TODO: 구현
    return {"result": query}


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    print(f"Starting MCP server on :{os.environ.get('MCP_PORT', '8001')} ({transport})")
    mcp.run(transport=transport)
