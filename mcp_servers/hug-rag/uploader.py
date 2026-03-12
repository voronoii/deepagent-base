#!/usr/bin/env python3
"""HUG RAG 데이터 업로더 - JSONL 파일을 Qdrant에 임베딩하여 업로드합니다."""

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# ── 설정 ──────────────────────────────────────────
EMBED_MODEL_PATH = os.environ.get(
    "EMBED_MODEL",
    "/DATA3/users/mj/hf_models/snowflake-arctic-embed-l-v2.0-ko",
)
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "7000"))
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "hug_docs")
EMBED_DEVICE = os.environ.get("EMBED_DEVICE", None)
VECTOR_SIZE = 1024
MAX_CHUNK_LEN = 2000
CHUNK_OVERLAP = 200
BATCH_SIZE = 100

DATA_DIRS = {
    "law": "/DATA3/users/mj/hug/data/법령2",
    "guide": "/DATA3/users/mj/hug/data/카테고리별기본자료",
    "manual": "/DATA3/users/mj/hug/data/매뉴얼_v2",
}


# ── JSONL 파싱 ────────────────────────────────────
def parse_law_line(obj: dict, source_file: str) -> Dict[str, Any]:
    """법령 JSONL 라인을 통합 스키마로 변환."""
    return {
        "domain": "law",
        "title": obj.get("law_title", ""),
        "sub_title": obj.get("sub_title", ""),
        "text": obj.get("text", ""),
        "source_file": source_file,
        "category": obj.get("law_type", ""),
        "law_type": obj.get("law_type"),
        "pub_date": obj.get("pub_date"),
        "jo_link_url": obj.get("jo_link_url"),
    }


def parse_guide_line(obj: dict, source_file: str) -> Dict[str, Any]:
    """가이드/매뉴얼 JSONL 라인을 통합 스키마로 변환."""
    tags = obj.get("tags", {})
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except (json.JSONDecodeError, TypeError):
            tags = {}
    return {
        "domain": "guide",
        "title": tags.get("source", "") or source_file,
        "sub_title": obj.get("title", ""),
        "text": obj.get("text", ""),
        "source_file": source_file,
        "category": tags.get("categories", ""),
        "law_type": None,
        "pub_date": None,
        "jo_link_url": None,
    }


def load_jsonl_files(data_dir: str, domain: str) -> List[Dict[str, Any]]:
    """디렉토리 내 모든 JSONL 파일을 파싱."""
    docs = []
    data_path = Path(data_dir)
    if not data_path.exists():
        print(f"  [SKIP] 디렉토리 없음: {data_dir}")
        return docs

    for jsonl_file in sorted(data_path.glob("*.jsonl")):
        source_name = jsonl_file.stem
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if domain == "law":
                    doc = parse_law_line(obj, source_name)
                else:
                    doc = parse_guide_line(obj, source_name)

                if doc["text"].strip():
                    docs.append(doc)

        print(f"  {source_name}: {sum(1 for d in docs if d['source_file'] == source_name)}건")

    return docs


# ── 텍스트 처리 ───────────────────────────────────
def build_contextual_text(doc: Dict[str, Any]) -> str:
    """문맥 prefix를 붙인 임베딩용 텍스트 생성."""
    parts = []
    if doc["title"]:
        parts.append(doc["title"])
    if doc["sub_title"]:
        parts.append(doc["sub_title"])
    prefix = " > ".join(parts)
    if prefix:
        return f"{prefix}. {doc['text']}"
    return doc["text"]


def split_long_text(text: str, max_len: int = MAX_CHUNK_LEN, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """긴 텍스트를 overlap 있게 분할."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_len
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks


# ── Qdrant 업로드 ─────────────────────────────────
def create_points(docs: List[Dict[str, Any]], model: SentenceTransformer) -> List[models.PointStruct]:
    """문서 리스트를 Qdrant PointStruct로 변환."""
    points = []

    for doc in tqdm(docs, desc="임베딩 생성"):
        contextual_text = build_contextual_text(doc)
        chunks = split_long_text(contextual_text)

        for chunk_idx, chunk in enumerate(chunks):
            vector = model.encode(chunk, show_progress_bar=False).tolist()
            unique_key = f"{doc['domain']}_{doc['source_file']}_{doc['sub_title']}_{chunk_idx}"
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_key))

            payload = {
                "domain": doc["domain"],
                "title": doc["title"],
                "sub_title": doc["sub_title"],
                "text": doc["text"] if chunk_idx == 0 else chunk,
                "source_file": doc["source_file"],
                "category": doc["category"],
            }
            if doc["law_type"]:
                payload["law_type"] = doc["law_type"]
            if doc["pub_date"]:
                payload["pub_date"] = doc["pub_date"]
            if doc["jo_link_url"]:
                payload["jo_link_url"] = doc["jo_link_url"]

            points.append(models.PointStruct(id=point_id, vector=vector, payload=payload))

    return points


def batch_upsert(client: QdrantClient, collection: str, points: List[models.PointStruct]):
    """배치 단위로 Qdrant에 업로드."""
    for i in tqdm(range(0, len(points), BATCH_SIZE), desc="Qdrant 업로드"):
        batch = points[i : i + BATCH_SIZE]
        try:
            client.upsert(collection_name=collection, points=batch)
        except Exception as e:
            print(f"  배치 업로드 오류 (batch {i // BATCH_SIZE + 1}): {e}")


def main():
    print("=== HUG RAG 데이터 업로더 ===\n")

    # 1. 모델 로드
    print(f"임베딩 모델 로드: {EMBED_MODEL_PATH}")
    model = SentenceTransformer(EMBED_MODEL_PATH, device=EMBED_DEVICE)

    # 2. Qdrant 연결
    print(f"Qdrant 연결: {QDRANT_HOST}:{QDRANT_PORT}")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # 3. 컬렉션 생성 (기존 삭제 후 재생성)
    print(f"컬렉션 '{COLLECTION_NAME}' 설정...")
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"  기존 컬렉션 삭제됨")
    except Exception:
        pass

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
    )
    print(f"  새 컬렉션 생성됨\n")

    # 4. JSONL 파일 로드
    all_docs = []
    for domain, data_dir in DATA_DIRS.items():
        print(f"[{domain}] {data_dir}")
        docs = load_jsonl_files(data_dir, domain)
        all_docs.extend(docs)
        print(f"  소계: {len(docs)}건\n")

    print(f"총 문서 수: {len(all_docs)}건\n")

    if not all_docs:
        print("로드된 문서가 없습니다.")
        return

    # 5. 임베딩 및 포인트 생성
    points = create_points(all_docs, model)
    print(f"\n총 포인트 수: {len(points)}건 (청크 분할 포함)\n")

    # 6. Qdrant 업로드
    batch_upsert(client, COLLECTION_NAME, points)

    # 7. Payload 인덱스 생성
    print("\nPayload 인덱스 생성...")
    client.create_payload_index(COLLECTION_NAME, "domain", models.PayloadSchemaType.KEYWORD)
    client.create_payload_index(COLLECTION_NAME, "title", models.PayloadSchemaType.TEXT)
    client.create_payload_index(COLLECTION_NAME, "category", models.PayloadSchemaType.KEYWORD)
    print("  domain, title, category 인덱스 생성 완료")

    # 8. 결과 확인
    info = client.get_collection(COLLECTION_NAME)
    print(f"\n=== 업로드 완료 ===")
    print(f"  컬렉션: {COLLECTION_NAME}")
    print(f"  포인트 수: {info.points_count}")
    print(f"  벡터 크기: {VECTOR_SIZE}")


if __name__ == "__main__":
    main()
