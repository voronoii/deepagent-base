# DeepAgent-Base 설정 가이드

Docker 배포 시 변경할 수 있는 모든 설정 포인트를 정리한 문서입니다.

---

## 1. `.env` — 최상위 환경변수 (가장 먼저 설정)

프로젝트 루트의 `.env` 파일은 `docker-compose.yml`이 참조하는 핵심 설정입니다.
`.env.example`을 복사하여 사용하세요: `cp .env.example .env`

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `MODEL_TYPE` | `vllm` | LLM 제공자 선택. `"openai"` 또는 `"vllm"` |
| `OPENAI_API_KEY` | (빈 값) | OpenAI API 키. `MODEL_TYPE=openai`일 때 필수 |
| `OPENAI_MODEL` | `gpt-4o` | 사용할 OpenAI 모델명 (예: `gpt-4o`, `gpt-4o-mini`) |
| `VLLM_BASE_URL` | `http://10.1.61.227:8002/v1` | vLLM 서버 주소. `MODEL_TYPE=vllm`일 때 사용 |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | 프론트엔드 → 백엔드 API 주소. **브라우저에서 접근하는 주소**이므로 서버 IP로 변경 필요 |
| `QDRANT_HOST` | `localhost` | Qdrant 벡터DB 호스트 (MCP 서버들이 공유) |
| `QDRANT_PORT` | `7000` | Qdrant 포트 |

### 팀원 설정 체크리스트

```bash
# 1. .env 파일 생성
cp .env.example .env

# 2. 필수 수정 항목
NEXT_PUBLIC_API_URL=http://<서버IP>:8000     # 서버 외부 IP로 변경
MODEL_TYPE=openai                             # 또는 vllm
OPENAI_API_KEY=sk-...                         # openai 사용 시 필수
VLLM_BASE_URL=http://<vllm서버IP>:8002/v1    # vllm 사용 시 서버 주소
QDRANT_HOST=<서버IP>                          # ⚠️ 반드시 호스트 IP (localhost 불가, 아래 설명 참고)
QDRANT_PORT=7000                              # Qdrant 포트
```

---

## 2. `backend/config.py` — 백엔드 모델 설정

`.env`의 환경변수를 읽어 LLM 모델 인스턴스를 생성합니다. 직접 수정이 필요한 경우는 드뭅니다.

| 변수 | 환경변수 | 기본값 | 설명 |
|------|---------|--------|------|
| `MODEL_TYPE` | `MODEL_TYPE` | `vllm` | 모델 제공자 (`openai` / `vllm`) |
| `OPENAI_API_KEY` | `OPENAI_API_KEY` | `""` | OpenAI API 키 |
| `OPENAI_MODEL` | `OPENAI_MODEL` | `gpt-4o` | OpenAI 모델명 |
| `OPENAI_MAX_CONTEXT_TOKENS` | (하드코딩) | `128,000` | OpenAI 모델 컨텍스트 윈도우 크기 |
| `VLLM_BASE_URL` | `VLLM_BASE_URL` | `http://10.1.61.227:8002/v1` | vLLM 서버 엔드포인트 |
| `VLLM_API_KEY` | (하드코딩) | `dummy` | vLLM은 인증 불필요 |
| `VLLM_MODEL` | (하드코딩) | `default` | vLLM 모델명 |
| `VLLM_MAX_CONTEXT_TOKENS` | (하드코딩) | `32,768` | vLLM 모델 컨텍스트 윈도우 크기 |
| `AGENT_ROOT_DIR` | `AGENT_ROOT_DIR` | `/DATA3/users/mj/DeepAgent-Base` | 에이전트 루트 디렉토리 (Docker 내에서는 `/app`) |
| `AGENTS_MD_PATH` | (하드코딩) | `./backend/AGENTS.md` | 에이전트 메모리 파일 경로 |

> **참고**: Docker 환경에서는 `docker-compose.yml`의 `environment`에서 `AGENT_ROOT_DIR=/app`으로 자동 설정됩니다.

---

## 3. `backend/mcp_config.json` — MCP 도구 선택

에이전트가 사용할 MCP 서버(도구)를 제어합니다. **에이전트에게 특정 도구만 제공하려면 이 파일을 수정하세요.**

```json
{
  "servers": [
    {
      "name": "news",
      "enabled": true,
      "transport": "streamable_http",
      "url": "http://localhost:1879/mcp/",
      "url_docker": "http://mcp-news:1879/mcp/",
      "description": "부동산 뉴스 검색 MCP 서버"
    }
  ]
}
```

### 각 서버 설정 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string | 서버 식별자. 도구 이름 접두사로 사용됨 (`mcp__{name}__{tool}`) |
| `enabled` | boolean | **`true`/`false`로 도구 활성화/비활성화**. 가장 간편한 도구 관리 방법 |
| `transport` | string | 전송 방식. 현재 모든 서버가 `streamable_http` 사용 |
| `url` | string | 로컬 개발용 URL (Docker 없이 실행 시) |
| `url_docker` | string | Docker 네트워크 내부 URL. `DOCKER_ENV=1`이면 이 주소 사용 |
| `description` | string | 서버 설명 (로그/대시보드용) |

### 현재 등록된 MCP 서버

| 서버 | 포트 | 설명 | docker-compose 서비스명 |
|------|------|------|------------------------|
| `news` | 1879 | 부동산 뉴스 검색 | `mcp-news` |
| `hug-rag` | 1883 | 전세/부동산 법령 및 보증보험 가이드 RAG | `mcp-hug-rag` |

### 도구 관리 방법

- **특정 도구 비활성화**: 해당 서버의 `"enabled": false`로 변경
- **새 도구 추가**: `servers` 배열에 새 항목 추가 + `docker-compose.yml`에 서비스 추가
- **Docker 환경 자동 감지**: 백엔드가 `DOCKER_ENV=1`이면 `url_docker`를, 아니면 `url`을 사용

> **참고**: `docker-compose.yml`에 서비스가 있어도 이 파일에 등록하지 않으면 에이전트는 해당 도구를 사용할 수 없습니다.

---

## 4. `docker-compose.yml` — Docker 서비스 구성

### 4.1 백엔드 (`backend`)

```yaml
backend:
  ports:
    - "8000:8000"             # 외부포트:내부포트
  environment:
    - MODEL_TYPE=${MODEL_TYPE:-vllm}
    - OPENAI_API_KEY=${OPENAI_API_KEY:-}
    - OPENAI_MODEL=${OPENAI_MODEL:-gpt-4o}
    - VLLM_BASE_URL=${VLLM_BASE_URL:-http://10.1.61.227:8002/v1}
    - AGENT_ROOT_DIR=/app
    - DOCKER_ENV=1            # MCP 연결 시 url_docker 사용하도록 설정
```

| 환경변수 | 설명 |
|---------|------|
| `MODEL_TYPE` | `.env`에서 주입 |
| `OPENAI_API_KEY` | `.env`에서 주입 |
| `OPENAI_MODEL` | `.env`에서 주입 |
| `VLLM_BASE_URL` | `.env`에서 주입 |
| `AGENT_ROOT_DIR` | Docker 내 앱 경로. 항상 `/app` |
| `DOCKER_ENV` | `1`로 설정되면 `mcp_config.json`의 `url_docker` 사용 |

### 4.2 프론트엔드 (`frontend`)

```yaml
frontend:
  build:
    args:
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
  ports:
    - "3111:3111"             # 웹 UI 접속 포트
```

| 설정 | 설명 |
|------|------|
| `NEXT_PUBLIC_API_URL` | **빌드 타임**에 주입됨. Next.js 빌드 시 고정되므로 `.env`에서 반드시 올바른 값 설정 필요 |
| 포트 `3111` | 브라우저에서 접근하는 웹 UI 포트 |

> **주의**: `NEXT_PUBLIC_API_URL`은 빌드 시점에 결정됩니다. 변경 후 반드시 `docker compose build frontend`를 다시 실행하세요.

### 4.3 MCP 서버 공통 패턴

모든 MCP 서버는 동일한 Dockerfile(`mcp_servers/Dockerfile`)을 공유하며, `TOOL_DIR` ARG로 어떤 서버를 빌드할지 결정합니다.

```yaml
mcp-<서버명>:
  build:
    context: ./mcp_servers
    args:
      TOOL_DIR: <서버 디렉토리명>    # mcp_servers/ 하위 디렉토리
  ports:
    - "<외부포트>:<내부포트>"
  environment:
    - MCP_PORT=<포트>               # server.py가 리슨하는 포트
    # ... 서버별 추가 환경변수
```

### 4.4 각 MCP 서버별 환경변수

#### `mcp-news` (포트 1879)

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `MCP_PORT` | `1879` | 서버 리슨 포트 |

#### `mcp-hug-rag` (포트 1883) — 전세/법령 RAG 검색

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `MCP_PORT` | `1883` | 서버 리슨 포트 |
| `QDRANT_HOST` | `localhost` | Qdrant 호스트 |
| `QDRANT_PORT` | `7000` | Qdrant 포트 |
| `QDRANT_COLLECTION` | `hug_docs` | Qdrant 컬렉션명 |
| `EMBED_MODEL` | (볼륨 마운트 경로) | 임베딩 모델 경로 |
| `RERANKER_MODEL` | (볼륨 마운트 경로) | 리랭커 모델 경로 |
| `EMBED_DEVICE` | `None` (자동) | PyTorch 디바이스 (`cuda`, `cpu` 등) |
| `RERANKER_DEVICE` | `None` (자동) | 리랭커 디바이스 |
| `RETRIEVAL_TOP_K` | `20` | 벡터 검색 시 후보 수 (리랭킹 전) |
| `LOG_LEVEL` | `INFO` | 로그 레벨 |

**볼륨 마운트** (모델 파일):
```yaml
volumes:
  - /DATA3/users/mj/hf_models/snowflake-arctic-embed-l-v2.0-ko:/models/snowflake-arctic-embed-l-v2.0-ko:ro
  - /DATA3/users/mj/hf_models/bge-reranker-v2-m3-ko:/models/bge-reranker-v2-m3-ko:ro
```

> **팀원 설정**: 모델 파일이 다른 경로에 있으면 볼륨 마운트의 왼쪽(호스트 경로)을 변경하세요.
> 예: `/home/user/models/snowflake-arctic-embed-l-v2.0-ko:/models/snowflake-arctic-embed-l-v2.0-ko:ro`

#### `mcp-apt-metadata` (포트 1880) — 아파트 메타데이터

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `MCP_PORT` | `1880` | 서버 리슨 포트 |
| `APT_METADATA_PKL` | `.pkl 파일 경로` | 아파트 메타데이터 Pickle 파일 |
| `DONG_EXCEL_PATH` | `.xlsx 파일 경로` | 법정동 정보 Excel 파일 |
| `QDRANT_HOST` | `localhost` | Qdrant 호스트 |
| `QDRANT_PORT` | `7000` | Qdrant 포트 |
| `QDRANT_COLLECTION` | `apt_reviews` | Qdrant 컬렉션명 |
| `EMBED_MODEL` | (로컬 경로) | 임베딩 모델 경로 |
| `EMBED_SERVER_URL` | (빈 값) | 원격 임베딩 서버 URL (선택) |

#### `mcp-apt-review` (포트 1881) — 아파트 리뷰 검색

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `MCP_PORT` | `1881` | 서버 리슨 포트 |
| `QDRANT_HOST` | `localhost` | Qdrant 호스트 |
| `QDRANT_PORT` | `7000` | Qdrant 포트 |
| `QDRANT_COLLECTION` | `apt_reviews` | Qdrant 컬렉션명 |
| `EMBED_MODEL` | (로컬 경로) | 임베딩 모델 경로 |
| `EMBED_SERVER_URL` | (빈 값) | 원격 임베딩 서버 URL (선택) |
| `REVIEW_FULL_PASS_THRESHOLD` | `50` | 전수 검색 임계값 |
| `REVIEW_VECTOR_TOP_K` | `30` | 벡터 검색 후보 수 |

#### `mcp-apt-develop` (포트 1882) — 개발사업 정보

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `MCP_PORT` | `1882` | 서버 리슨 포트 |
| `BEOPJUNGDONG_TXT` | `.txt 파일 경로` | 법정동코드 전체자료 파일 |

---

## 5. `mcp_servers/Dockerfile` — MCP 서버 공통 Dockerfile

```dockerfile
FROM python:3.11-slim
ARG TOOL_DIR                    # docker-compose의 build.args.TOOL_DIR로 주입
WORKDIR /app
COPY ${TOOL_DIR}/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ${TOOL_DIR}/ .
ENV MCP_HOST=0.0.0.0            # 모든 인터페이스에서 리슨
ENV MCP_TRANSPORT=streamable-http  # MCP 전송 방식
CMD ["python", "server.py"]
```

| 설정 | 설명 |
|------|------|
| `TOOL_DIR` | 빌드 시 결정. `mcp_servers/` 하위 디렉토리명 |
| `MCP_HOST` | 서버 바인드 주소. Docker에서는 `0.0.0.0` 필수 |
| `MCP_TRANSPORT` | `streamable-http` 고정 |

---

## 6. `backend/AGENTS.md` — 에이전트 행동 지시서

에이전트의 역할, 위임 규칙, 응답 형식을 정의하는 프롬프트 파일입니다.
파일 경로: `backend/AGENTS.md`

수정하면 에이전트의 행동 패턴이 변경됩니다:
- 오케스트레이터의 위임 전략
- 서브에이전트 사용 규칙
- 응답 형식 및 언어 설정
- 데이터 카드 형식

---

## 7. `backend/agent.py` — 에이전트 프롬프트 (코드 내)

에이전트 시스템 프롬프트가 코드에 직접 작성되어 있습니다. 에이전트 동작을 세밀하게 조정하려면 이 파일을 수정합니다.

| 프롬프트 | 위치 | 설명 |
|---------|------|------|
| `ORCHESTRATOR_PROMPT` | `agent.py:19` | 오케스트레이터 행동 규칙. 요청 분류, 위임 전략, MCP 도구 설명 자동 주입 |
| `RESEARCH_AGENT_PROMPT` | `agent.py:73` | 리서치 에이전트. 검색 전략 (MCP 우선 → DuckDuckGo 폴백) |
| `REPORT_WRITER_PROMPT` | `agent.py:104` | 리포트 작성 에이전트. 보고서 구조 및 형식 |

> **참고**: MCP 도구 목록은 서버 시작 시 자동으로 프롬프트에 주입됩니다. 수동 추가 불필요.

---

## 8. 네트워크 및 포트 요약

### Docker Compose 포트 매핑

| 서비스 | 외부 포트 | 용도 |
|--------|----------|------|
| `frontend` | `3111` | 웹 UI (브라우저 접속) |
| `backend` | `8000` | API 서버 |
| `mcp-news` | `1879` | 뉴스 MCP |
| `mcp-apt-metadata` | `1880` | 아파트 메타데이터 MCP |
| `mcp-apt-review` | `1881` | 아파트 리뷰 MCP |
| `mcp-apt-develop` | `1882` | 개발사업 MCP |
| `mcp-hug-rag` | `1883` | 전세/법령 RAG MCP |

### 외부 의존 서비스

| 서비스 | 기본 주소 | 설명 |
|--------|----------|------|
| Qdrant | `<호스트IP>:7000` | 벡터 데이터베이스 (별도 실행 필요, 아래 섹션 참고) |
| vLLM 서버 | `10.1.61.227:8002` | vLLM 추론 서버 (MODEL_TYPE=vllm일 때) |
| OpenAI API | `api.openai.com` | OpenAI (MODEL_TYPE=openai일 때) |

### Docker 내부 네트워크

모든 서비스는 `deepagent` 브릿지 네트워크로 연결됩니다.
서비스 간 통신은 **서비스명**으로 접근합니다 (예: `http://mcp-news:1879`).

---

## 9. Qdrant 벡터 데이터베이스 설정

RAG 기반 MCP 서버(`hug-rag`, `apt-metadata`, `apt-review`)는 Qdrant를 사용합니다.
Qdrant는 Docker Compose에 포함되지 않으며 **호스트에서 별도로 실행**해야 합니다.

### 9.1 Qdrant 설치 및 실행

```bash
# Docker로 실행 (권장)
docker run -d --name qdrant \
  -p 7000:6333 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# 또는 이미 실행 중인 Qdrant가 있으면 그 주소를 사용
```

### 9.2 `.env`에서 Qdrant 연결 설정

```bash
QDRANT_HOST=<호스트IP>    # 예: 10.1.61.229
QDRANT_PORT=7000
```

> **⚠️ 중요: `QDRANT_HOST=localhost`를 사용하면 안 됩니다!**
>
> Docker 컨테이너 내부에서 `localhost`는 **컨테이너 자신**을 가리킵니다.
> 호스트 머신에서 실행 중인 Qdrant에 접근하려면 반드시 **호스트의 실제 IP**를 사용하세요.
>
> ```
> # ❌ 잘못된 설정 (컨테이너 → 컨테이너 자신 → Connection refused)
> QDRANT_HOST=localhost
>
> # ✅ 올바른 설정 (컨테이너 → 호스트 머신의 Qdrant)
> QDRANT_HOST=10.1.61.229
> ```
>
> 호스트 IP 확인: `hostname -I | awk '{print $1}'`

### 9.3 데이터 업로드 (컬렉션 생성)

Qdrant에 데이터가 없으면 MCP 서버가 빈 결과를 반환합니다.
각 MCP 서버에 맞는 데이터를 업로드해야 합니다.

```bash
# 예: hug-rag 데이터 업로드
cd mcp_servers/hug-rag
pip install -r requirements.txt
python uploader.py
```

`uploader.py`는 호스트에서 직접 실행합니다 (Docker 밖에서).
환경변수로 Qdrant 주소를 지정할 수 있습니다:

```bash
QDRANT_HOST=localhost QDRANT_PORT=7000 python uploader.py
```

> **참고**: 업로더는 호스트에서 실행하므로 `localhost`로 접근 가능합니다.
> Docker 컨테이너 내부의 MCP 서버만 호스트 IP가 필요합니다.

### 9.4 연결 상태 확인

```bash
# 방법 1: MCP 대시보드에서 확인
# http://<서버IP>:8000/mcp/dashboard

# 방법 2: 컨테이너 내부에서 직접 테스트
docker compose exec mcp-hug-rag python -c "
from qdrant_client import QdrantClient
import os
host = os.environ.get('QDRANT_HOST', 'localhost')
port = int(os.environ.get('QDRANT_PORT', '7000'))
try:
    c = QdrantClient(host=host, port=port, timeout=3)
    collections = c.get_collections().collections
    for col in collections:
        info = c.get_collection(col.name)
        print(f'  {col.name}: {info.points_count} points')
    print(f'OK: Qdrant 연결 성공 ({host}:{port})')
except Exception as e:
    print(f'FAIL: {e}')
"
```

### 9.5 새 도메인에서 Qdrant 사용하기

다른 도메인의 데이터로 RAG MCP 서버를 새로 만들 때:

1. **컬렉션 분리**: 도메인별로 별도 컬렉션 사용 (예: `hug_docs`, `apt_reviews`)
2. **업로더 작성**: `mcp_servers/hug-rag/uploader.py`를 참고하여 JSONL → Qdrant 업로드 스크립트 작성
3. **환경변수로 컬렉션명 지정**: `QDRANT_COLLECTION` 환경변수로 컬렉션명 설정
4. **동일 Qdrant 인스턴스 공유 가능**: 여러 MCP 서버가 같은 Qdrant를 공유하되, 컬렉션명만 다르게 설정

```yaml
# docker-compose.yml 예시 — 새 RAG MCP 서버
mcp-my-domain:
  build:
    context: ./mcp_servers
    args:
      TOOL_DIR: my-domain
  ports:
    - "1884:1884"
  environment:
    - MCP_PORT=1884
    - QDRANT_HOST=${QDRANT_HOST:-localhost}     # .env에서 호스트 IP 주입
    - QDRANT_PORT=${QDRANT_PORT:-7000}
    - QDRANT_COLLECTION=my_domain_docs          # 도메인별 컬렉션명
    - EMBED_MODEL=/models/snowflake-arctic-embed-l-v2.0-ko
  volumes:
    - /path/to/models/snowflake-arctic-embed-l-v2.0-ko:/models/snowflake-arctic-embed-l-v2.0-ko:ro
  networks:
    - deepagent
```

### 9.6 Qdrant 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| MCP 도구가 에러 반환, 에이전트가 DuckDuckGo로 폴백 | `QDRANT_HOST=localhost` (Docker 내부에서 접근 불가) | `.env`에서 `QDRANT_HOST=<호스트IP>`로 변경 후 `docker compose up -d` |
| `Connection refused` | Qdrant가 실행 중이지 않거나 포트가 다름 | Qdrant 실행 상태 확인, `QDRANT_PORT` 확인 |
| 검색 결과가 비어있음 | 컬렉션에 데이터 미업로드 | `uploader.py` 실행하여 데이터 업로드 |
| MCP 대시보드에서 `online`인데 도구가 안 됨 | 대시보드 health check는 MCP 서버 포트만 확인 (Qdrant 연결은 미확인) | 위의 컨테이너 내부 테스트 명령어로 Qdrant 연결 직접 확인 |
| `Collection not found` | 컬렉션명 불일치 | `QDRANT_COLLECTION` 환경변수와 업로더에서 사용한 컬렉션명 확인 |

---

## 10. 빠른 시작 가이드

### 최소 설정 (OpenAI 모델 사용)

```bash
# 1. 환경변수 설정
cat > .env << 'EOF'
MODEL_TYPE=openai
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o
NEXT_PUBLIC_API_URL=http://<서버IP>:8000
QDRANT_HOST=<서버IP>
QDRANT_PORT=7000
EOF

# 2. Qdrant 실행 (이미 실행 중이면 생략)
docker run -d --name qdrant -p 7000:6333 qdrant/qdrant

# 3. 데이터 업로드 (필요한 MCP 서버에 대해)
cd mcp_servers/hug-rag && pip install -r requirements.txt && python uploader.py && cd ../..

# 4. 사용할 MCP 도구 선택 (backend/mcp_config.json에서 enabled 조정)

# 5. 빌드 및 실행
docker compose build
docker compose up -d

# 6. 접속
# 웹 UI: http://<서버IP>:3111
# API: http://<서버IP>:8000
# MCP 대시보드: http://<서버IP>:8000/mcp/dashboard
```

### vLLM 모델 사용

```bash
cat > .env << 'EOF'
MODEL_TYPE=vllm
VLLM_BASE_URL=http://<vllm서버IP>:8002/v1
NEXT_PUBLIC_API_URL=http://<서버IP>:8000
QDRANT_HOST=<서버IP>
QDRANT_PORT=7000
EOF
```

### 필수 외부 서비스

- **Qdrant**: MCP 서버가 벡터 검색에 사용. **반드시 호스트 IP로 설정** (섹션 9 참고)
- **HuggingFace 모델 파일**: RAG 서버의 볼륨 마운트 경로에 모델 필요
  - `snowflake-arctic-embed-l-v2.0-ko` (임베딩, 1024차원)
  - `bge-reranker-v2-m3-ko` (리랭커)
  - 다운로드: `huggingface-cli download dragonkue/snowflake-arctic-embed-l-v2.0-ko --local-dir ./models/snowflake-arctic-embed-l-v2.0-ko`

---

## 11. 설정 변경 시 주의사항

| 변경 항목 | 필요한 작업 |
|----------|------------|
| `.env` 수정 | `docker compose up -d` (자동 반영) |
| `NEXT_PUBLIC_API_URL` 변경 | `docker compose build frontend` 후 `up -d` (빌드 타임 변수) |
| `mcp_config.json` 수정 | `docker compose restart backend` |
| MCP 서버 코드 수정 | `docker compose build <서비스명>` 후 `up -d` |
| `AGENTS.md` 수정 | `docker compose restart backend` |
| `agent.py` 프롬프트 수정 | `docker compose build backend` 후 `up -d` |
| 볼륨 마운트 경로 변경 | `docker-compose.yml` 수정 후 `up -d` |
| 새 MCP 서버 추가 | `docker-compose.yml`에 서비스 추가 + `mcp_config.json`에 등록 + `docker compose up -d` |

---

## 12. 새 MCP 서버 추가 체크리스트

1. `mcp_servers/<서버명>/` 디렉토리 생성 (`_template/` 복사)
2. `server.py`, `requirements.txt` 구현
3. `docker-compose.yml`에 서비스 추가 (포트 충돌 주의)
4. `backend/mcp_config.json`에 서버 등록 (`enabled: true`)
5. `docker compose build` → `docker compose up -d`
6. `http://<서버IP>:8000/mcp/dashboard`에서 연결 상태 확인
