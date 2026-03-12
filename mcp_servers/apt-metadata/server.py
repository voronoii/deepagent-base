"""Apartment metadata MCP server - 아파트 메타데이터 검색 도구."""

import json
import logging
import os
import pickle
import threading
import time
from typing import Any, Dict, List, Optional
from urllib import error as url_error
from urllib import request as url_request

import numpy as np
import pandas as pd
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ── 환경 변수 ──────────────────────────────────────
APT_METADATA_PKL = os.environ.get(
    "APT_METADATA_PKL",
    "/DATA3/users/mj/spatial/data/total_apt_list_0716_df.pkl",
)
DONG_EXCEL_PATH = os.environ.get(
    "DONG_EXCEL_PATH",
    "/DATA3/users/mj/spatial/crawl_hogang/data/서울시_법정동_호갱노노id_위경도.xlsx",
)
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

mcp = FastMCP(
    "apt-metadata",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "1880")),
)

# ── 데이터 캐시 (lazy-load 싱글턴) ──────────────────
_df_apartments: pd.DataFrame | None = None
_df_dongs: pd.DataFrame | None = None


def _load_apartments() -> pd.DataFrame:
    global _df_apartments
    if _df_apartments is not None:
        return _df_apartments
    with open(APT_METADATA_PKL, "rb") as f:
        _df_apartments = pickle.load(f)
    for col in ["type", "sub_type", "dong", "status"]:
        if col in _df_apartments.columns:
            _df_apartments[col] = _df_apartments[col].astype("category")
    if "id" in _df_apartments.columns:
        _df_apartments.set_index("id", inplace=True, drop=False)
    logger.info("아파트 메타데이터 로드: %d건", len(_df_apartments))
    return _df_apartments


def _load_dongs() -> pd.DataFrame:
    global _df_dongs
    if _df_dongs is not None:
        return _df_dongs
    _df_dongs = pd.read_excel(DONG_EXCEL_PATH)
    _df_dongs.dropna(subset=["법정동명"], inplace=True)
    logger.info("법정동 데이터 로드: %d건", len(_df_dongs))
    return _df_dongs


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


# ── MCP 도구 ────────────────────────────────────────
@mcp.tool()
def search_apartments(
    name: str = "",
    dong: str = "",
    gu: str = "",
    min_households: int = 0,
    max_households: int = 0,
    min_year: int = 0,
    max_year: int = 0,
    min_parking_ratio: float = 0.0,
    limit: int = 100,
) -> dict:
    """
    아파트 메타데이터를 조건(이름, 동, 구, 세대수, 준공년도, 주차비율)에 따라 검색합니다.

    Args:
        name: 아파트 이름 (부분 매칭, 예: '래미안')
        dong: 법정동 (예: '청파동')
        gu: 자치구 (예: '마포구')
        min_households: 최소 세대수
        max_households: 최대 세대수
        min_year: 최소 준공년도
        max_year: 최대 준공년도
        min_parking_ratio: 최소 주차비율
        limit: 최대 반환 건수 (기본 100)
    """
    t0 = time.time()
    df = _load_apartments()
    result = df.copy()

    if name:
        result = result[result["name"].str.contains(name, case=False, na=False)]
    if dong:
        result = result[result["dong"] == dong]
    if gu:
        result = result[result["address"].str.contains(gu, na=False)]
    if min_households and "totalHousehold" in result.columns:
        result = result[result["totalHousehold"] >= min_households]
    if max_households and "totalHousehold" in result.columns:
        result = result[result["totalHousehold"] <= max_households]
    if min_year and "aptYear" in result.columns:
        result = result[result["aptYear"] >= min_year]
    if max_year and "aptYear" in result.columns:
        result = result[result["aptYear"] <= max_year]
    if min_parking_ratio and "parkingRatio" in result.columns:
        result = result[result["parkingRatio"] >= min_parking_ratio]

    result = result.head(limit)
    rows: List[Dict[str, Any]] = []
    for _, row in result.iterrows():
        rows.append(
            {
                "아파트ID": row.get("id", "N/A"),
                "아파트명": row.get("name", "N/A"),
                "주소": row.get("address", "N/A"),
                "동": row.get("dong", "N/A"),
                "세대수": int(row.get("totalHousehold", 0))
                if pd.notna(row.get("totalHousehold"))
                else 0,
                "준공년도": int(row.get("aptYear", 0))
                if pd.notna(row.get("aptYear"))
                else 0,
                "주차비율": float(row.get("parkingRatio", 0))
                if pd.notna(row.get("parkingRatio"))
                else 0,
            }
        )

    return {
        "소요시간": f"{time.time() - t0:.2f}초",
        "검색개수": len(rows),
        "결과": rows,
    }


@mcp.tool()
def get_apartment_details(apt_id: str) -> dict:
    """
    특정 아파트의 상세 정보를 반환합니다.

    Args:
        apt_id: 아파트 ID (예: 'f4M87')
    """
    df = _load_apartments()

    if apt_id in df.index:
        row = df.loc[apt_id]
    else:
        matched = df[df["id"] == apt_id]
        if matched.empty:
            return {"오류": f"아파트 ID {apt_id}를 찾을 수 없습니다"}
        row = matched.iloc[0]

    details = {}
    for col in row.index:
        val = row[col]
        if pd.isna(val):
            details[col] = None
        elif isinstance(val, (np.integer, np.floating)):
            details[col] = int(val) if isinstance(val, np.integer) else float(val)
        else:
            details[col] = str(val)

    return {"아파트ID": apt_id, "상세정보": details}


@mcp.tool()
def find_correct_dong_name(query_dong: str) -> dict:
    """
    사용자 입력 지역명에서 가장 유사한 실제 법정동명을 반환합니다.
    오타나 유사한 이름도 매칭합니다.

    Args:
        query_dong: 검색할 동 이름 (예: '청파동', '마포구')
    """
    from thefuzz import process

    df = _load_dongs()
    dong_list = df["법정동명"].unique().tolist()
    best_match, score = process.extractOne(query_dong, dong_list)
    return {"입력동명": query_dong, "추천동명": best_match, "유사도": score}


@mcp.tool()
def find_apartment_by_name(
    apt_name: str,
    address_filter: str = "",
    limit: int = 5,
) -> dict:
    """
    아파트 이름으로 벡터 유사도 검색을 수행합니다.
    오타, 부분 이름, 유사 이름도 매칭합니다.
    아파트의 apt_id, 정확한 이름, 주소를 반환합니다.

    Args:
        apt_name: 검색할 아파트 이름 (예: '래미안푸르지오', '힐스테이트')
        address_filter: 주소 범위 필터 (예: '마포구')
        limit: 반환할 최대 아파트 수 (기본 5)
    """
    from qdrant_client import QdrantClient, models

    t0 = time.time()
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    vec = _embed_single(apt_name)

    search_filter = None
    if address_filter:
        search_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="apt_address",
                    match=models.MatchText(text=address_filter),
                )
            ]
        )

    hits = client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=models.NamedVector(name="aptname_vector", vector=vec),
        query_filter=search_filter,
        limit=100,
        with_payload=True,
    )

    seen: Dict[str, Dict[str, Any]] = {}
    for sp in hits:
        pl = sp.payload or {}
        aid = pl.get("apt_id", "")
        if aid and aid not in seen:
            seen[aid] = {
                "아파트ID": aid,
                "아파트명": pl.get("apt_name", "N/A"),
                "주소": pl.get("apt_address", "N/A"),
                "유사도": f"{(sp.score or 0.0):.3f}",
            }
        if len(seen) >= limit:
            break

    results = list(seen.values())
    return {
        "소요시간": f"{time.time() - t0:.2f}초",
        "검색개수": len(results),
        "결과": results,
    }


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    print(f"Starting apt-metadata MCP server on :{os.environ.get('MCP_PORT', '1880')} ({transport})")
    mcp.run(transport=transport)
