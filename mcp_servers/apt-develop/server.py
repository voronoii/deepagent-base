"""Apartment development MCP server - 정비사업(재개발/재건축) 현황 조회 도구."""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# ── 환경 변수 ──────────────────────────────────────
BEOPJUNGDONG_TXT = os.environ.get(
    "BEOPJUNGDONG_TXT",
    "/DATA3/users/mj/spatial/data/법정동코드 전체자료.txt",
)

mcp = FastMCP(
    "apt-develop",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "1882")),
)


# ── 내부 헬퍼 ───────────────────────────────────────
def _get_codes(region_name: str) -> List[str]:
    lines = open(BEOPJUNGDONG_TXT, encoding="utf-8").readlines()
    active_seoul = [
        line.strip() for line in lines if "폐지" not in line and "서울" in line
    ]

    code_map: Dict[str, str] = {}
    for line in active_seoul:
        parts = line.split("\t")
        addr_parts = parts[1].split(" ")
        if len(addr_parts) <= 1:
            continue
        addr = " ".join(addr_parts[1:])
        code_map[addr] = parts[0]

    return [code_map[key] for key in code_map if region_name in key]


def _fetch_one_code(
    code: str, idx: int, total: int
) -> Tuple[List[pd.DataFrame], Optional[Exception]]:
    url = (
        f"https://cleanup.seoul.go.kr/cleanup/bsnssttus/lsubBsnsSttus.do?"
        "bsnsSeCodeList=100&bsnsSeCodeList=101&bsnsSeCodeList=102&"
        "bsnsSeCodeList=103&bsnsSeCodeList=104&bsnsSeCodeList=105&"
        "bsnsSeCodeList=106&bsnsEfctMthdList=1&bsnsEfctMthdList=2&"
        "bsnsEfctMthdList=3&bsnsEfctMthdList=4&operSeCodeList=100&"
        "operSeCodeList=101&operSeCodeList=102&operSeCodeList=103&"
        "cafeSttusCodeList=100&cafeSttusCodeList=110&"
        "scupBsnsSttus.bsnsProgrsSttusCode=&scupBsnsSttus.asscNm=&"
        f"scupBsnsSttus.signguCode={code[:5]}&scupBsnsSttus.legaldongCode={code[5:]}&"
        "sortColumn=&orderValue="
    )
    try:
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        local_dfs: List[pd.DataFrame] = []
        for table in soup.find_all("table"):
            headers = [th.text.strip() for th in table.find_all("th")]
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.text.strip() for td in tr.find_all("td")]
                if cells:
                    rows.append(cells)
            if len(rows) <= 1:
                continue
            local_dfs.append(pd.DataFrame(rows, columns=headers if headers else None))
        return local_dfs, None
    except Exception as exc:
        logger.warning("[%d/%d] code=%s 크롤링 실패: %s", idx + 1, total, code, exc)
        return [], exc


# ── MCP 도구 ────────────────────────────────────────
@mcp.tool()
def get_develop_docs(region_name: str) -> dict:
    """
    법정동 이름을 입력받아 해당 지역의 정비사업(재개발/재건축) 현황을 반환합니다.
    서울시 클린업 시스템 기반.

    Args:
        region_name: 지역 법정동 이름 (예: '마포구', '청파동')
    """
    t0 = time.time()
    codes = _get_codes(region_name)
    if not codes:
        return {
            "success": False,
            "message": f"'{region_name}' 지역에서 정비사업 데이터를 찾을 수 없습니다.",
            "data": [],
            "total_count": 0,
        }

    dfs: List[pd.DataFrame] = []
    crawl_success = 0
    crawl_fail = 0
    total = len(codes)

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_code = {
            executor.submit(_fetch_one_code, code, idx, total): code
            for idx, code in enumerate(codes)
        }
        for future in as_completed(future_to_code):
            local_dfs, exc = future.result()
            if exc is None:
                dfs.extend(local_dfs)
                crawl_success += 1
            else:
                crawl_fail += 1

    if not dfs:
        return {
            "success": False,
            "message": f"'{region_name}' 지역에서 정비사업 데이터를 찾을 수 없습니다.",
            "data": [],
            "total_count": 0,
        }

    combined = pd.concat(dfs, ignore_index=True)
    return {
        "success": True,
        "data": combined.to_dict("records"),
        "columns": combined.columns.tolist(),
        "total_count": len(combined),
        "region_name": region_name,
    }


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    print(f"Starting apt-develop MCP server on :{os.environ.get('MCP_PORT', '1882')} ({transport})")
    mcp.run(transport=transport)
