"""Apartment review MCP server - 아파트 리뷰 검색 도구."""

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List
from urllib import error as url_error
from urllib import request as url_request

import numpy as np
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ── 환경 변수 ──────────────────────────────────────
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "7000"))
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "apt_reviews")
EMBED_MODEL_PATH = os.environ.get(
    "EMBED_MODEL",
    "/DATA3/users/mj/hf_models/snowflake-arctic-embed-l-v2.0-ko",
)
EMBED_CACHE_DIR = os.environ.get(
    "EMBED_CACHE_DIR",
    "/DATA3/users/mj/spatial/agent_workflow/cache",
)
EMBED_SERVER_URL = os.environ.get("EMBED_SERVER_URL", "")
EMBED_DEVICE = os.environ.get("EMBED_DEVICE", None)
REVIEW_FULL_PASS_THRESHOLD = int(os.environ.get("REVIEW_FULL_PASS_THRESHOLD", "50"))
REVIEW_VECTOR_TOP_K = int(os.environ.get("REVIEW_VECTOR_TOP_K", "30"))

mcp = FastMCP(
    "apt-review",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "1881")),
)

# ── 임베딩 헬퍼 ─────────────────────────────────────
_embed_model = None
_embed_lock = threading.Lock()
_remote_disabled = False


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        with _embed_lock:
            if _embed_model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("임베딩 모델 로드: %s", EMBED_MODEL_PATH)
                _embed_model = SentenceTransformer(
                    EMBED_MODEL_PATH,
                    cache_folder=EMBED_CACHE_DIR,
                    device=EMBED_DEVICE,
                )
    return _embed_model


def _embed_single(text: str) -> List[float]:
    global _remote_disabled
    if EMBED_SERVER_URL and not _remote_disabled:
        try:
            payload = json.dumps({"texts": [text]}).encode("utf-8")
            req = url_request.Request(
                EMBED_SERVER_URL.rstrip("/") + "/embed",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with url_request.urlopen(req, timeout=10.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            vectors = body.get("vectors") or (
                [body["vector"]] if "vector" in body else None
            )
            if vectors:
                return vectors[0]
        except Exception:
            logger.warning("원격 임베딩 실패, 로컬 폴백")
            _remote_disabled = True
    model = _get_embed_model()
    return model.encode(
        [text], convert_to_numpy=True, show_progress_bar=False
    ).tolist()[0]


# ── Qdrant 클라이언트 (싱글턴) ──────────────────────
_client = None


def _get_client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient

        logger.info("Qdrant 연결: %s:%s, collection=%s", QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION)
        _client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _client


# ── 결과 포맷 헬퍼 ──────────────────────────────────
def _format_point(sp) -> Dict[str, Any]:
    pl = sp.payload or {}
    text = pl.get("text", "") or ""
    return {
        "점수": f"{(sp.score or 0.0):.3f}",
        "주소": pl.get("apt_address", "N/A"),
        "아파트명": pl.get("apt_name", "N/A"),
        "아파트ID": pl.get("apt_id", "N/A"),
        "리뷰": text[:300] + ("..." if len(text) > 300 else ""),
    }


def _format_record(rec) -> Dict[str, Any]:
    pl = rec.payload or {}
    text = pl.get("text", "") or ""
    return {
        "점수": "N/A",
        "주소": pl.get("apt_address", "N/A"),
        "아파트명": pl.get("apt_name", "N/A"),
        "아파트ID": pl.get("apt_id", "N/A"),
        "리뷰": text[:300] + ("..." if len(text) > 300 else ""),
    }


# ── MCP 도구 ────────────────────────────────────────
@mcp.tool()
def search_reviews(
    query_text: str = "",
    apt_name: str = "",
    apt_id: str = "",
    address_filter: str = "",
    region: str = "",
    limit: int = 100,
) -> dict:
    """
    아파트 리뷰를 검색합니다.

    적응적 검색 전략:
    - 필터 결과 50건 이하이면 전체 리뷰를 반환 (벡터 서치 생략)
    - 필터 결과 50건 초과이면 query_text 기반 벡터 서치로 상위 결과 반환

    최소한 address_filter, region, apt_id, apt_name 중 하나는 필요합니다.

    Args:
        query_text: 검색 테마 (예: '주차', '소음', '교통')
        apt_name: 아파트 이름 (예: '래미안푸르지오')
        apt_id: 아파트 ID (예: 'f4M87')
        address_filter: 주소 필터 (예: '용산구 한남동')
        region: 지역구 필터 (예: '마포구')
        limit: 최대 반환 건수 (기본 100)
    """
    from qdrant_client import models

    t0 = time.time()
    client = _get_client()

    base_conditions: List[models.Condition] = []

    if address_filter:
        base_conditions.append(
            models.FieldCondition(
                key="apt_address", match=models.MatchText(text=address_filter)
            )
        )
    if region:
        base_conditions.append(
            models.FieldCondition(
                key="apt_address", match=models.MatchText(text=region)
            )
        )
    if apt_id:
        base_conditions.append(
            models.FieldCondition(key="apt_id", match=models.MatchValue(value=apt_id))
        )

    if not base_conditions and not apt_name:
        return {
            "오류": "최소한 address_filter, region, apt_id, apt_name 중 하나는 필요합니다."
        }

    # ── apt_name → aptname_vector 로 apt_id 후보 추출 ──
    if apt_name and not apt_id:
        try:
            apt_vec = _embed_single(apt_name)
            search_filter = (
                models.Filter(must=base_conditions) if base_conditions else None
            )
            apt_candidates = client.search(
                collection_name=QDRANT_COLLECTION,
                query_vector=models.NamedVector(name="aptname_vector", vector=apt_vec),
                query_filter=search_filter,
                limit=20,
                with_payload=True,
            )
            seen: set[str] = set()
            for sp in apt_candidates:
                aid = (sp.payload or {}).get("apt_id")
                if aid and aid not in seen:
                    seen.add(aid)
            apt_ids_candidate = list(seen)
            if apt_ids_candidate:
                base_conditions.append(
                    models.FieldCondition(
                        key="apt_id", match=models.MatchAny(any=apt_ids_candidate)
                    )
                )
        except Exception:
            logger.exception("apt_name 후보 검색 실패")

    scroll_filter = models.Filter(must=base_conditions) if base_conditions else None

    # ── 리뷰 수에 따라 적응적 전략 분기 ──
    scrolled, _next_offset = client.scroll(
        collection_name=QDRANT_COLLECTION,
        scroll_filter=scroll_filter,
        limit=REVIEW_FULL_PASS_THRESHOLD + 1,
        with_payload=True,
        with_vectors=False,
    )
    total_in_scope = len(scrolled)

    if total_in_scope == 0:
        return {
            "소요시간": f"{time.time() - t0:.2f}초",
            "검색개수": 0,
            "검색전략": "필터 결과 없음",
            "결과": [],
            "메시지": "해당 조건에 맞는 리뷰가 없습니다.",
        }

    # 전략 A: FULL PASS (리뷰 수 ≤ threshold)
    if total_in_scope <= REVIEW_FULL_PASS_THRESHOLD:
        if _next_offset is not None:
            remaining, _ = client.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter=scroll_filter,
                limit=500,
                offset=_next_offset,
                with_payload=True,
                with_vectors=False,
            )
            scrolled.extend(remaining)

        results = [_format_record(rec) for rec in scrolled[:limit]]
        return {
            "소요시간": f"{time.time() - t0:.2f}초",
            "검색개수": len(results),
            "검색전략": f"전체 전달 (리뷰 {total_in_scope}건 ≤ {REVIEW_FULL_PASS_THRESHOLD}건)",
            "결과": results,
        }

    # 전략 B: query_text 없음 → 필터만
    if not query_text:
        all_records, _ = client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        results = [_format_record(rec) for rec in all_records]
        return {
            "소요시간": f"{time.time() - t0:.2f}초",
            "검색개수": len(results),
            "검색전략": f"필터만 (query_text 없음, 리뷰 {total_in_scope}건+)",
            "결과": results,
        }

    # 전략 C: VECTOR SEARCH (리뷰 수 > threshold + query_text 있음)
    theme_vec = _embed_single(query_text)

    try:
        hits = client.search(
            collection_name=QDRANT_COLLECTION,
            query_vector=models.NamedVector(name="review_vector", vector=theme_vec),
            query_filter=scroll_filter,
            limit=REVIEW_VECTOR_TOP_K,
            with_payload=True,
        )
        results = [_format_point(sp) for sp in hits]
    except Exception:
        logger.warning("review_vector 검색 실패 — 로컬 재랭킹 폴백")
        all_records = []
        offset = None
        while True:
            batch, offset = client.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter=scroll_filter,
                limit=500,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_records.extend(batch)
            if offset is None:
                break

        theme_arr = np.asarray(theme_vec)
        scored = []
        for rec in all_records:
            text = (rec.payload or {}).get("text", "")
            if not text:
                continue
            r_vec = np.asarray(_embed_single(text))
            denom = (np.linalg.norm(r_vec) * np.linalg.norm(theme_arr)) + 1e-8
            score = float(np.dot(theme_arr, r_vec) / denom)
            scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, rec in scored[:REVIEW_VECTOR_TOP_K]:
            d = _format_record(rec)
            d["점수"] = f"{score:.3f}"
            results.append(d)

    return {
        "소요시간": f"{time.time() - t0:.2f}초",
        "검색개수": len(results),
        "검색전략": f"벡터 서치 (리뷰 {total_in_scope}건+ > {REVIEW_FULL_PASS_THRESHOLD}건)",
        "결과": results,
    }


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    print(f"Starting apt-review MCP server on :{os.environ.get('MCP_PORT', '1881')} ({transport})")
    mcp.run(transport=transport)
