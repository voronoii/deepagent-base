# DeepAgent-Base 개선 실행 계획

> **작성일**: 2026-03-05
> **기반**: 팀 코드리뷰 종합 보고서 (아키텍트, 코드 리뷰어, 옵저버빌리티 전문가)

---

## 실행 순서

의존성과 심각도를 기반으로 **반드시 아래 순서대로** 진행합니다.
앞 단계의 결과물이 뒷 단계의 전제 조건이 됩니다.

---

### Step 1. 환경 설정 기반 정비 [CRITICAL]

> 뒤의 모든 Step이 이 설정에 의존합니다. 가장 먼저 수행.

**변경 파일**: `backend/config.py`, `.env.example`, `docker-compose.yml`

**작업 내용**:

1-1. `config.py` — 하드코딩 제거, 모든 설정을 환경변수화
```python
# Before
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://10.1.61.227:8002/v1")
VLLM_API_KEY = "dummy"
VLLM_MODEL = "default"

# After
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8002/v1")
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "dummy")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "default")
MAX_CONTEXT_TOKENS = int(os.environ.get("MAX_CONTEXT_TOKENS", "32768"))
```

1-2. `.env.example` — 전체 설정 항목 문서화
```bash
# === vLLM ===
VLLM_BASE_URL=http://localhost:8002/v1
VLLM_API_KEY=dummy
VLLM_MODEL=default
MAX_CONTEXT_TOKENS=32768

# === 보안 ===
ALLOWED_ORIGINS=http://localhost:3000
API_KEY=                          # 비어있으면 인증 비활성화

# === 체크포인터 ===
CHECKPOINT_DB=./data/checkpoints.db

# === LangSmith 트레이싱 ===
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=deepagent-base

# === 프론트엔드 ===
NEXT_PUBLIC_API_URL=http://localhost:8000
```

1-3. `docker-compose.yml` — 새 환경변수 전달
```yaml
backend:
  environment:
    - VLLM_BASE_URL=${VLLM_BASE_URL:-http://localhost:8002/v1}
    - VLLM_API_KEY=${VLLM_API_KEY:-dummy}
    - ALLOWED_ORIGINS=${ALLOWED_ORIGINS:-http://localhost:3000}
    - API_KEY=${API_KEY:-}
    - CHECKPOINT_DB=${CHECKPOINT_DB:-/app/data/checkpoints.db}
    - LANGCHAIN_TRACING_V2=${LANGCHAIN_TRACING_V2:-false}
    - LANGCHAIN_API_KEY=${LANGCHAIN_API_KEY:-}
    - LANGCHAIN_PROJECT=${LANGCHAIN_PROJECT:-deepagent-base}
```

**완료 기준**: `config.py`에 하드코딩 IP/상수가 0개

---

### Step 2. 보안 기본값 수정 [CRITICAL]

> Step 1의 환경변수(`ALLOWED_ORIGINS`, `API_KEY`)에 의존

**변경 파일**: `backend/main.py`

**작업 내용**:

2-1. CORS 제한
```python
# Before (main.py:31-37)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# After
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)
```

2-2. API Key 인증 미들웨어 (선택적 활성화)
```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    expected_key = os.environ.get("API_KEY")
    # API_KEY가 설정되지 않으면 인증 비활성화 (개발 모드)
    if expected_key:
        # health 엔드포인트는 인증 제외
        if request.url.path not in ("/api/health", "/api/mcp/health", "/mcp/dashboard"):
            api_key = request.headers.get("X-API-Key")
            if api_key != expected_key:
                return JSONResponse(status_code=401, content={"error": "Invalid API key"})
    return await call_next(request)
```

**완료 기준**: `allow_origins=["*"]` 제거, API Key 설정 시 인증 필요

---

### Step 3. 체크포인터 영속화 [CRITICAL]

> Step 1의 환경변수(`CHECKPOINT_DB`)에 의존

**변경 파일**: `backend/agent.py`, `docker-compose.yml`, `backend/requirements.txt`

**작업 내용**:

3-1. `requirements.txt`에 추가
```
aiosqlite>=0.20.0
```

3-2. `agent.py` — MemorySaver 교체
```python
# Before (agent.py:145)
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()

# After
import os
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

CHECKPOINT_DB = os.environ.get("CHECKPOINT_DB", "./data/checkpoints.db")

async def get_checkpointer():
    """영속 체크포인터 생성. 서버 재시작 후에도 대화 이력 유지."""
    os.makedirs(os.path.dirname(CHECKPOINT_DB), exist_ok=True)
    return AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB)
```

3-3. `main.py` — startup에서 checkpointer 초기화
```python
# lifespan 내 (Step 5에서 전환)
checkpointer = await get_checkpointer()
_orchestrator = create_orchestrator(checkpointer=checkpointer)
```

3-4. `agent.py` — create_orchestrator에 checkpointer 파라미터 추가
```python
def create_orchestrator(checkpointer=None):
    # ...
    agent = create_deep_agent(
        # ...
        checkpointer=checkpointer,
    )
```

3-5. `docker-compose.yml` — 볼륨 마운트
```yaml
backend:
  volumes:
    - checkpoint-data:/app/data
volumes:
  checkpoint-data:
```

**완료 기준**: 서버 재시작 후 기존 thread_id로 대화 이력 유지 확인

---

### Step 4. FilesystemBackend 보안 강화 [HIGH]

> 독립적, 단일 라인 변경

**변경 파일**: `backend/agent.py`

**작업 내용**:
```python
# Before (agent.py:197)
backend=FilesystemBackend(root_dir=AGENT_ROOT_DIR)

# After
backend=FilesystemBackend(root_dir=AGENT_ROOT_DIR, virtual_mode=True)
```

**완료 기준**: DeprecationWarning 미발생, 에이전트 root_dir 외부 접근 불가

---

### Step 5. 모듈 초기화 안정화 [HIGH]

> Step 3의 checkpointer 비동기화에 의존

**변경 파일**: `backend/agent.py`, `backend/main.py`

**작업 내용**:

5-1. 모듈 레벨 사이드이펙트 제거 (`agent.py`)
```python
# Before (agent.py:102, 106) — import 시점에 실행
search_tool = DuckDuckGoSearchRun()
_subagent_model = get_model(max_tokens=2048)

research_agent_spec = { ... "tools": [search_tool], "model": _subagent_model }
report_writer_spec = { ... "model": _subagent_model }

# After — create_orchestrator() 내부로 이동
def create_orchestrator(checkpointer=None):
    search_tool = DuckDuckGoSearchRun()
    subagent_model = get_model(max_tokens=2048)

    research_tools = [search_tool]
    mcp_tools = mcp_manager.get_tools()
    if mcp_tools:
        research_tools.extend(mcp_tools)

    research_agent_spec = {
        "name": "research-agent",
        "description": "...",
        "system_prompt": RESEARCH_AGENT_PROMPT,
        "tools": research_tools,
        "model": subagent_model,
    }
    report_writer_spec = {
        "name": "report-writer-agent",
        "description": "...",
        "system_prompt": REPORT_WRITER_PROMPT,
        "model": subagent_model,
    }
    # ... create_deep_agent 호출
```

5-2. deprecated lifecycle API 교체 (`main.py`)
```python
# Before (main.py:44, 65)
@app.on_event("startup")
async def startup_event(): ...

@app.on_event("shutdown")
async def shutdown_event(): ...

# After
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    await mcp_manager.initialize()
    checkpointer = await get_checkpointer()
    _orchestrator = create_orchestrator(checkpointer=checkpointer)
    logger.info("Orchestrator agent ready.")
    yield
    await mcp_manager.shutdown()

app = FastAPI(lifespan=lifespan, ...)
```

**완료 기준**: vLLM 미응답 시에도 `import backend.agent` 성공, deprecated warning 미발생

---

### Step 6. LangSmith 트레이싱 활성화 [HIGH]

> Step 1의 .env.example에 이미 추가됨. 코드 변경 없음.

**변경 파일**: 없음 (환경변수만)

**작업 내용**:

Step 1에서 `.env.example`과 `docker-compose.yml`에 이미 `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`를 추가했으므로, `.env`에 실제 값을 설정하면 즉시 활성화됩니다.

```bash
# .env (실제 배포 시)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_실제키값
LANGCHAIN_PROJECT=deepagent-base-prod
```

**활성화 시 자동으로 추적되는 항목**:
- 오케스트레이터 ↔ 서브에이전트 전체 호출 체인
- 각 LLM 호출의 입력/출력 토큰
- 도구 호출 인자와 결과
- 에이전트별 실행 시간

**완료 기준**: LangSmith 대시보드에서 에이전트 트레이스 확인

---

### Step 7. SSE 스트리밍 안정화 [MEDIUM]

> Step 5의 lifespan 전환 이후 수행

**변경 파일**: `backend/main.py`

**작업 내용**:

7-1. 스트리밍 타임아웃 추가
```python
STREAM_TIMEOUT = int(os.environ.get("STREAM_TIMEOUT", "300"))  # 5분

async def _stream_agent_response(message: str, thread_id: str):
    start_time = time.monotonic()
    # ... 기존 코드
    async for chunk in _orchestrator.astream(...):
        if time.monotonic() - start_time > STREAM_TIMEOUT:
            logger.warning("Stream timeout for thread=%s after %ds", thread_id, STREAM_TIMEOUT)
            yield _sse_event("error", {"error": "Processing timeout", "timeout": STREAM_TIMEOUT})
            break
        # ... 기존 처리
```

7-2. SummarizationMiddleware 요약 이벤트 감지
```python
from langchain_core.messages import HumanMessage

# 메시지 순회 루프 내 추가
if isinstance(msg, HumanMessage):
    if getattr(msg, "additional_kwargs", {}).get("lc_source") == "summarization":
        logger.info("Context compaction triggered for thread=%s", thread_id)
        yield _sse_event("reasoning_step", {
            "name": "Context Compaction",
            "status": "completed",
            "description": "대화 이력이 자동 요약되었습니다.",
            "timestamp": _now_iso(),
        })
```

**완료 기준**: 5분 초과 시 타임아웃 이벤트 발생, 요약 시 프론트엔드에 알림

---

### Step 8. MCP 서버 설정 개선 [MEDIUM]

> 독립적

**변경 파일**: `mcp_servers/news/server.py`

**작업 내용**:
```python
# Before (server.py:30)
url = "https://qt.some.co.kr/TrendMap/JSON/ServiceHandler?"

# After
NEWS_API_URL = os.environ.get(
    "NEWS_API_URL",
    "https://qt.some.co.kr/TrendMap/JSON/ServiceHandler?"
)
# ... 함수 내에서 NEWS_API_URL 사용
```

**완료 기준**: 환경변수로 API URL 교체 가능

---

### Step 9. 테스트 인프라 구축 [HIGH]

> Step 3, 5 완료 후 (lazy init + async checkpointer 적용된 코드 기준으로 테스트 작성)

**새 파일**: `tests/conftest.py`, `tests/test_config.py`, `tests/test_agent.py`, `tests/test_streaming.py`

**작업 내용**:

9-1. `pyproject.toml` — dev 의존성 추가
```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "httpx>=0.27"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

9-2. `tests/conftest.py` — 공통 fixtures
```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_llm():
    """vLLM 없이 테스트 가능한 mock LLM"""
    llm = MagicMock()
    llm.profile = {"max_input_tokens": 32768}
    return llm

@pytest.fixture
def mock_mcp_manager():
    """MCP 서버 없이 테스트 가능한 mock manager"""
    manager = AsyncMock()
    manager.get_tools.return_value = []
    return manager
```

9-3. 최소 테스트 케이스
- `test_config.py`: 환경변수 기본값 검증, model.profile 설정 확인
- `test_agent.py`: create_orchestrator() 호출 시 에러 없음 (mock LLM)
- `test_streaming.py`: SSE 이벤트 형식 검증 (`_sse_event`, `_extract_text_content`)

**완료 기준**: `pytest tests/` 실행 시 전체 pass

---

### Step 10. SkillsMiddleware 도입 [MEDIUM]

> Step 4 (virtual_mode) 완료 후. 파일 시스템 기반 스킬 로딩에 의존.

**변경 파일**: `backend/agent.py`
**새 디렉토리**: `skills/common/`, `skills/real_estate/`

**작업 내용**:

10-1. 공통 스킬 디렉토리 생성
```
skills/
├── common/
│   └── SKILL.md          # 모든 고객 공통 워크플로우
└── real_estate/
    └── SKILL.md          # 부동산 도메인 전용
```

10-2. `agent.py` — create_deep_agent에 skills 전달
```python
SKILLS_DIRS = os.environ.get("SKILLS_DIRS", "./skills/common/")

agent = create_deep_agent(
    ...
    skills=SKILLS_DIRS.split(","),
)
```

**완료 기준**: 에이전트가 SKILL.md 기반 워크플로우를 인식하고 활용

---

### Step 11. 구조화 로깅 [MEDIUM]

> Step 5의 lifespan 전환 이후

**변경 파일**: `backend/main.py`, `backend/requirements.txt`

**작업 내용**:

11-1. `requirements.txt`에 추가
```
python-json-logger>=2.0.0
```

11-2. `main.py` — 로깅 포맷 전환
```python
import os
from pythonjsonlogger import jsonlogger

LOG_FORMAT = os.environ.get("LOG_FORMAT", "text")  # "text" or "json"

if LOG_FORMAT == "json":
    handler = logging.StreamHandler()
    handler.setFormatter(jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    ))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
```

**완료 기준**: `LOG_FORMAT=json` 설정 시 JSON 로그 출력

---

### Step 12. 멀티테넌트 팩토리 패턴 [MEDIUM]

> Step 3 (async checkpointer), Step 5 (lazy init), Step 10 (skills) 모두 완료 후

**변경 파일**: `backend/agent.py`, `backend/main.py`, `backend/schemas.py`

**이 Step은 아키텍처 변경이 크므로 별도 설계가 필요합니다.**

핵심 아이디어:
```python
# agent.py
from functools import lru_cache

@lru_cache(maxsize=32)
def get_orchestrator(tenant_id: str):
    config = load_tenant_config(tenant_id)
    return create_orchestrator(
        system_prompt=config.system_prompt,
        subagents=config.subagents,
        root_dir=f"/data/tenants/{tenant_id}",
        skills=[f"./skills/common/", f"./skills/{config.domain}/"],
        checkpointer=checkpointer,
    )

# schemas.py — tenant_id 추가
class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"
    tenant_id: str = "default"  # 새 필드

# main.py — 테넌트별 에이전트 라우팅
orchestrator = get_orchestrator(request.tenant_id)
```

**완료 기준**: 서로 다른 tenant_id로 다른 프롬프트/도구를 사용하는 에이전트 실행

---

## 실행 순서 의존성 다이어그램

```
Step 1 (환경 설정)
  ├── Step 2 (CORS/인증) ── 의존: ALLOWED_ORIGINS, API_KEY
  ├── Step 3 (체크포인터) ── 의존: CHECKPOINT_DB
  │     └── Step 5 (모듈 초기화) ── 의존: async checkpointer
  │           ├── Step 7 (SSE 안정화) ── 의존: lifespan 전환
  │           ├── Step 9 (테스트) ── 의존: lazy init 코드
  │           └── Step 11 (JSON 로깅) ── 의존: lifespan 전환
  ├── Step 4 (virtual_mode) ── 독립적
  │     └── Step 10 (Skills) ── 의존: virtual_mode 설정
  ├── Step 6 (LangSmith) ── 의존: .env.example
  └── Step 8 (MCP 설정) ── 독립적

Step 12 (멀티테넌트) ── 의존: Step 3 + 5 + 10 모두 완료
```

---

## 변경 파일 요약

| 파일 | 관련 Step | 변경 유형 |
|------|----------|----------|
| `backend/config.py` | 1 | 수정 (환경변수화) |
| `.env.example` | 1 | 수정 (전체 설정 문서화) |
| `docker-compose.yml` | 1, 3 | 수정 (환경변수 + 볼륨) |
| `backend/main.py` | 2, 5, 7, 11 | 수정 (CORS, lifespan, 타임아웃, 로깅) |
| `backend/agent.py` | 3, 4, 5, 10, 12 | 수정 (checkpointer, virtual_mode, lazy init, skills) |
| `backend/requirements.txt` | 3, 11 | 수정 (aiosqlite, python-json-logger) |
| `mcp_servers/news/server.py` | 8 | 수정 (URL 환경변수화) |
| `backend/schemas.py` | 12 | 수정 (tenant_id 추가) |
| `pyproject.toml` | 9 | 수정 (dev 의존성) |
| `tests/*` | 9 | 신규 (테스트 파일) |
| `skills/*` | 10 | 신규 (스킬 디렉토리) |
