"""HUG RAG MCP server - 전세/부동산 법령·가이드 검색 도구."""

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from qdrant_client import QdrantClient, models

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ── 환경 변수 ──────────────────────────────────────
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "7000"))
COLLECTION = os.environ.get("QDRANT_COLLECTION", "hug_docs")
EMBED_MODEL_PATH = os.environ.get(
    "EMBED_MODEL",
    "/DATA3/users/mj/hf_models/snowflake-arctic-embed-l-v2.0-ko",
)
RERANKER_MODEL_PATH = os.environ.get(
    "RERANKER_MODEL",
    "/DATA3/users/mj/hf_models/bge-reranker-v2-m3-ko",
)
EMBED_DEVICE = os.environ.get("EMBED_DEVICE", None)
RERANKER_DEVICE = os.environ.get("RERANKER_DEVICE", None)
RETRIEVAL_TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "20"))

mcp = FastMCP(
    "hug-rag",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "1883")),
)

# ── Lazy 싱글턴 ────────────────────────────────────
_embed_model = None
_embed_lock = threading.Lock()
_reranker = None
_reranker_lock = threading.Lock()
_client = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        with _embed_lock:
            if _embed_model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("임베딩 모델 로드: %s", EMBED_MODEL_PATH)
                _embed_model = SentenceTransformer(EMBED_MODEL_PATH, device=EMBED_DEVICE)
    return _embed_model


def _get_reranker():
    global _reranker
    if _reranker is None:
        with _reranker_lock:
            if _reranker is None:
                try:
                    from sentence_transformers import CrossEncoder

                    logger.info("리랭커 모델 로드: %s", RERANKER_MODEL_PATH)
                    _reranker = CrossEncoder(RERANKER_MODEL_PATH, device=RERANKER_DEVICE)
                except Exception as e:
                    logger.warning("리랭커 로드 실패 (dense만 사용): %s", e)
                    _reranker = "unavailable"
    return _reranker


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        logger.info("Qdrant 연결: %s:%s", QDRANT_HOST, QDRANT_PORT)
        _client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _client


def _embed(text: str) -> List[float]:
    model = _get_embed_model()
    return model.encode(text, show_progress_bar=False).tolist()


def _rerank(query: str, docs: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """리랭커로 결과를 재정렬. 리랭커 없으면 원본 반환."""
    reranker = _get_reranker()
    if reranker == "unavailable" or not docs:
        return docs[:limit]

    pairs = [[query, d.get("text_for_rerank", d.get("조문/섹션내용", ""))] for d in docs]
    scores = reranker.predict(pairs)

    for i, doc in enumerate(docs):
        doc["rerank_score"] = float(scores[i])

    docs.sort(key=lambda x: x["rerank_score"], reverse=True)

    for doc in docs:
        doc.pop("text_for_rerank", None)
        doc.pop("rerank_score", None)

    return docs[:limit]


def _format_result(sp, include_full_text: bool = False) -> Dict[str, Any]:
    """Qdrant 검색 결과를 응답 포맷으로 변환."""
    pl = sp.payload or {}
    text = pl.get("text", "")
    result = {
        "유사도": f"{(sp.score or 0.0):.3f}",
        "도메인": pl.get("domain", "N/A"),
        "문서제목": pl.get("title", "N/A"),
        "조문/섹션명": pl.get("sub_title", "N/A"),
        "조문/섹션내용": text if include_full_text else (text[:500] + "..." if len(text) > 500 else text),
        "카테고리": pl.get("category", "N/A"),
        "출처파일": pl.get("source_file", "N/A"),
    }
    if pl.get("jo_link_url"):
        result["법령링크"] = pl["jo_link_url"]
    return result


# ── MCP 도구 ────────────────────────────────────────
@mcp.tool()
def search_hug_docs(
    query_text: str,
    domain: str = "",
    title_filter: str = "",
    limit: int = 5,
) -> dict:
    """
    전세 관련 법령 및 HUG 가이드 문서를 검색합니다.

    벡터 유사도 검색 + 리랭킹으로 가장 관련성 높은 문서를 반환합니다.

    Args:
        query_text: 검색 질의 (필수). 예: "전세보증금 반환 조건", "임대차 계약 해지 절차"
        domain: 도메인 필터 (선택). "law"=법령만, "guide"=가이드/매뉴얼만, ""=전체 검색.
                예: domain="law" → 법령 조문에서만 검색
                예: domain="guide" → HUG 가이드/매뉴얼에서만 검색
        title_filter: 특정 문서/법령명 필터 (선택). 예: "주택임대차보호법", "전세사기 피해예방"
        limit: 반환할 검색 결과 수 (기본값: 5)

    Returns:
        검색 결과 딕셔너리 (유사도, 문서제목, 조문/섹션명, 내용 등 포함)
    """
    logger.info(
        "search_hug_docs called: query_text=%r, domain=%r, title_filter=%r, limit=%d",
        query_text, domain, title_filter, limit,
    )
    t0 = time.time()
    client = _get_client()

    # 필터 조건 구성
    filter_conditions: List[models.Condition] = []

    if domain:
        filter_conditions.append(
            models.FieldCondition(key="domain", match=models.MatchValue(value=domain))
        )
    if title_filter:
        filter_conditions.append(
            models.FieldCondition(key="title", match=models.MatchText(text=title_filter))
        )

    search_filter = models.Filter(must=filter_conditions) if filter_conditions else None

    # dense 벡터 검색
    query_vector = _embed(query_text)
    search_result = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        query_filter=search_filter,
        limit=RETRIEVAL_TOP_K,
        with_payload=True,
    )
    hits = search_result.points

    if not hits:
        return {
            "소요시간": f"{time.time() - t0:.2f}초",
            "검색개수": 0,
            "결과": [],
            "메시지": "검색 결과가 없습니다.",
        }

    # 결과 포맷팅
    results = []
    for sp in hits:
        formatted = _format_result(sp)
        formatted["text_for_rerank"] = (sp.payload or {}).get("text", "")
        results.append(formatted)

    # 리랭킹
    results = _rerank(query_text, results, limit)

    return {
        "소요시간": f"{time.time() - t0:.2f}초",
        "검색개수": len(results),
        "결과": results,
    }


@mcp.tool()
def list_available_docs(domain: str = "") -> dict:
    """
    저장된 문서 목록을 조회합니다.

    Args:
        domain: 도메인 필터 (선택). "law"=법령만, "guide"=가이드/매뉴얼만, ""=전체

    Returns:
        문서 제목 목록과 도메인별 통계
    """
    client = _get_client()

    scroll_filter = None
    if domain:
        scroll_filter = models.Filter(
            must=[models.FieldCondition(key="domain", match=models.MatchValue(value=domain))]
        )

    all_records = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=scroll_filter,
            limit=500,
            offset=offset,
            with_payload=["domain", "title"],
            with_vectors=False,
        )
        all_records.extend(batch)
        if offset is None:
            break

    # 도메인별 고유 제목 수집
    doc_map: Dict[str, set] = {}
    for rec in all_records:
        pl = rec.payload or {}
        d = pl.get("domain", "unknown")
        t = pl.get("title", "unknown")
        doc_map.setdefault(d, set()).add(t)

    result = {}
    for d, titles in sorted(doc_map.items()):
        result[d] = sorted(titles)

    total = sum(len(v) for v in result.values())
    return {
        "총_문서수": total,
        "도메인별_문서목록": result,
    }


@mcp.tool()
def get_doc_by_title(
    title: str,
    sub_title: str = "",
    limit: int = 50,
) -> dict:
    """
    특정 문서/법령의 조문 또는 섹션을 정확히 조회합니다 (벡터 검색 없이 필터만 사용).

    Args:
        title: 문서/법령 제목 (필수). 예: "주택임대차보호법", "전세사기 피해예방 종합안내서"
        sub_title: 조문/섹션명 필터 (선택). 예: "제3조", "전세의 의미"
        limit: 최대 반환 건수 (기본 50)

    Returns:
        해당 문서의 조문/섹션 목록
    """
    client = _get_client()

    filter_conditions = [
        models.FieldCondition(key="title", match=models.MatchText(text=title))
    ]
    if sub_title:
        filter_conditions.append(
            models.FieldCondition(key="sub_title", match=models.MatchText(text=sub_title))
        )

    records, _ = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=models.Filter(must=filter_conditions),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    if not records:
        return {"오류": f"'{title}' 문서를 찾을 수 없습니다."}

    results = []
    for rec in records:
        pl = rec.payload or {}
        item = {
            "도메인": pl.get("domain", "N/A"),
            "문서제목": pl.get("title", "N/A"),
            "조문/섹션명": pl.get("sub_title", "N/A"),
            "조문/섹션내용": pl.get("text", ""),
            "카테고리": pl.get("category", "N/A"),
        }
        if pl.get("jo_link_url"):
            item["법령링크"] = pl["jo_link_url"]
        results.append(item)

    return {
        "문서제목": title,
        "검색개수": len(results),
        "결과": results,
    }


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    print(f"Starting hug-rag MCP server on :{os.environ.get('MCP_PORT', '1883')} ({transport})")
    mcp.run(transport=transport)
