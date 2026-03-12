"""News search MCP server - 부동산 뉴스 검색 도구."""

import os
import datetime
import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "news",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "1879")),
)


@mcp.tool()
def search_real_estate_news(
    keywords: str,
    date_range: int = 7,
) -> dict:
    """
    부동산 관련 뉴스를 검색합니다.

    Args:
        keywords: 검색할 키워드들을 &&로 연결한 문자열 (예: "마포구&&아파트&&전망")
        date_range: 검색할 날짜 범위 (기본값: 7일)

    Returns:
        검색된 뉴스 문서 리스트와 메타정보를 포함한 딕셔너리
    """
    url = "https://qt.some.co.kr/TrendMap/JSON/ServiceHandler?"

    dates = [
        (datetime.datetime.today() - datetime.timedelta(days=i)).strftime("%Y%m%d")
        for i in range(date_range)
    ]

    keyword_parts = keywords.split("&&")
    formatted_keywords = "&&".join([f"({kw.strip()})" for kw in keyword_parts])
    search_keyword = f"(#@VK#S2#부동산)&&{formatted_keywords}"

    all_documents = []
    total_pages_searched = 0

    for page_num in range(1, 10):
        params = {
            "lang": "ko",
            "source": "news",
            "startDate": dates[-1],
            "endDate": dates[0],
            "keyword": search_keyword,
            "rowPerPage": "1000",
            "pageNum": str(page_num),
            "orderType": "0",
            "command": "GetKeywordDocuments",
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            res = response.json()

            if "item" in res and "documentList" in res["item"]:
                doc_list = res["item"]["documentList"]

                if len(doc_list) == 0:
                    break

                for doc in doc_list:
                    doc_text = f"{doc.get('title', '')} {doc.get('content', '')}"
                    all_documents.append(doc_text)

                total_pages_searched += 1
            else:
                break

        except Exception as e:
            return {"success": False, "error": str(e), "documents": []}

    unique_documents = list(set(all_documents))[:20]

    return {
        "success": True,
        "documents": unique_documents,
        "metadata": {
            "total_count": len(unique_documents),
            "keywords": keywords,
            "date_range": date_range,
            "start_date": dates[-1],
            "end_date": dates[0],
            "pages_searched": total_pages_searched,
        },
    }


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    print(f"Starting news MCP server on :{os.environ.get('MCP_PORT', '1879')} ({transport})")
    mcp.run(transport=transport)
 