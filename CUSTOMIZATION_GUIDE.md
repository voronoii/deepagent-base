# DeepAgent-Base 커스터마이징 가이드

팀원들이 프로젝트를 자신의 환경과 용도에 맞게 커스텀하기 위한 가이드입니다.

---

## 프로젝트 구조

```
DeepAgent-Base/
├── backend/
│   ├── config.py          # [커스텀] LLM 서버 연결 설정
│   ├── agent.py           # [커스텀] 에이전트 구성 및 프롬프트
│   ├── AGENTS.md          # [커스텀] 에이전트 메모리 (컨텍스트 엔지니어링)
│   ├── mcp_config.json    # [커스텀] MCP 서버 설정
│   ├── mcp_tools.py       # [관리] MCP 도구 매니저
│   ├── main.py            # [관리] FastAPI 서버 + SSE 스트리밍
│   ├── schemas.py         # [관리] API 스키마 정의
│   └── __init__.py
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── globals.css    # [커스텀] 테마 색상, 폰트
│       │   ├── layout.tsx     # [관리] HTML 메타데이터
│       │   └── page.tsx       # [관리] 메인 페이지 로직
│       ├── components/        # [커스텀] UI 컴포넌트
│       ├── lib/api.ts         # [커스텀] API 엔드포인트 설정
│       └── types/index.ts     # [관리] 타입 정의
├── pyproject.toml             # [관리] Python 의존성
├── run.sh                     # [커스텀] 서버 실행 스크립트
└── CUSTOMIZATION_GUIDE.md     # 이 문서
```

---

## 1. LLM 서버 설정

**파일**: `backend/config.py`

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `VLLM_BASE_URL` | vLLM 서버 엔드포인트 | `http://10.1.61.227:8002/v1` |
| `VLLM_API_KEY` | API 키 (vLLM은 보통 불필요) | `"dummy"` |
| `VLLM_MODEL` | 사용할 모델명 | `"default"` |
| `AGENT_ROOT_DIR` | 에이전트 파일시스템 루트 경로 | `/DATA3/users/mj/DeepAgent-Base` |
| `AGENTS_MD_PATH` | 에이전트 메모리 파일 경로 | `./backend/AGENTS.md` |

### 커스텀 방법

```python
# OpenAI API 사용 시
VLLM_BASE_URL = "https://api.openai.com/v1"
VLLM_API_KEY = "sk-..."
VLLM_MODEL = "gpt-4o"

# 다른 vLLM 서버 사용 시
VLLM_BASE_URL = "http://your-server:8000/v1"
VLLM_MODEL = "your-model-name"
```

### 모델 파라미터 조정

`get_model()` 함수의 기본 파라미터:

| 파라미터 | 설명 | 기본값 | 권장 범위 |
|----------|------|--------|-----------|
| `temperature` | 응답 창의성 (낮을수록 일관적) | `0.1` | 0.0 ~ 1.0 |
| `max_tokens` | 오케스트레이터 최대 출력 토큰 | `4096` | 모델 한도 내 |

서브에이전트는 컨텍스트 초과 방지를 위해 `max_tokens=2048`로 별도 설정됨.

---

## 2. 에이전트 구성

**파일**: `backend/agent.py`

### 2.1 시스템 프롬프트 수정

세 가지 프롬프트를 용도에 맞게 수정할 수 있습니다:

| 변수 | 역할 | 수정 시 영향 |
|------|------|-------------|
| `ORCHESTRATOR_PROMPT` | 오케스트레이터의 행동 규칙 | 위임 전략, 응답 스타일, 언어 정책 |
| `RESEARCH_AGENT_PROMPT` | 리서치 에이전트의 조사 방식 | 검색 전략, 출력 형식 |
| `REPORT_WRITER_PROMPT` | 보고서 작성 에이전트의 작성 규칙 | 보고서 구조, 문체 |

**예시 — 도메인 특화 오케스트레이터:**

```python
ORCHESTRATOR_PROMPT = """\
You are a financial analysis orchestrator.
## Delegation Rules
- For market data gathering: delegate to "research-agent"
- For financial report writing: delegate to "report-writer-agent"
- Always include data cards for key financial metrics
## Domain Rules
- Present all monetary values in KRW and USD
- Include year-over-year comparisons
- Flag any data older than 30 days
"""
```

### 2.2 서브에이전트 추가/변경

새로운 서브에이전트를 추가하려면:

```python
# 1. 시스템 프롬프트 정의
CODE_REVIEWER_PROMPT = """\
You are a code review agent...
"""

# 2. 에이전트 스펙 정의
code_reviewer_spec = {
    "name": "code-reviewer-agent",
    "description": "코드 리뷰 에이전트. 코드 품질, 보안, 성능을 검토합니다.",
    "system_prompt": CODE_REVIEWER_PROMPT,
    "model": _subagent_model,  # 또는 get_model(max_tokens=3000) 등 별도 설정
    "tools": [],  # 필요한 도구 추가
}

# 3. create_orchestrator()에서 subagents 리스트에 추가
agent = create_deep_agent(
    ...
    subagents=[research_agent_spec, report_writer_spec, code_reviewer_spec],
    ...
)
```

### 2.3 도구(Tools) 추가

현재 사용 중인 도구: `DuckDuckGoSearchRun` (웹 검색)

LangChain 호환 도구를 추가할 수 있습니다:

```python
# 예시: Wikipedia 도구 추가
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

wiki_tool = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())

research_agent_spec = {
    ...
    "tools": [search_tool, wiki_tool],
}
```

### 2.4 체크포인터 변경

현재 `MemorySaver` (인메모리)를 사용 중. 서버 재시작 시 대화 이력이 사라짐.

```python
# SQLite 영구 저장으로 변경
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string("./sessions.db")

# PostgreSQL 사용 (프로덕션)
from langgraph.checkpoint.postgres import PostgresSaver
checkpointer = PostgresSaver.from_conn_string("postgresql://user:pass@host/db")
```

---

## 3. 에이전트 메모리 (컨텍스트 엔지니어링)

**파일**: `backend/AGENTS.md`

이 파일은 deepagents의 `MemoryMiddleware`에 의해 **모든 에이전트 호출마다** 시스템 프롬프트에 자동 주입됩니다. 에이전트의 장기 기억 역할을 합니다.

### 수정 가능 항목

| 섹션 | 용도 | 커스텀 포인트 |
|------|------|--------------|
| Identity | 에이전트 자기 인식 | 도메인, 역할 설명 변경 |
| Agent Architecture | 서브에이전트 사용법 | 에이전트 추가/제거 시 반영 |
| Workflow Patterns | 작업 패턴 | 도메인별 워크플로우 추가 |
| Task Delegation Guidelines | 위임 규칙 | 위임 조건 세분화 |
| Quality Standards | 품질 기준 | 도메인별 기준 추가 |
| Response Formatting | 응답 형식 | 데이터 카드 형식 변경 |
| Language Support | 다국어 | 대상 언어 변경 |

### 주의사항

- 이 파일은 매 호출마다 토큰을 소비하므로 **간결하게** 유지
- vLLM 모델의 max_model_len(32768)을 고려하여 너무 길지 않게 작성
- 변경 시 서버 재시작 필요 없음 (FilesystemBackend가 매번 읽음)

---

## 4. 프론트엔드 테마

**파일**: `frontend/src/app/globals.css`

### 색상 커스텀

```css
@theme inline {
  --color-primary: #2b6cee;      /* 메인 강조색 (버튼, 링크, 아이콘) */
  --color-bg-dark: #101622;      /* 전체 배경색 */
  --color-panel-dark: #1a2233;   /* 패널/카드 배경색 */
  --color-border-dark: #232f48;  /* 테두리 색상 */
  --color-bg-light: #f6f6f8;    /* 라이트 모드용 (미사용) */
  --font-sans: "Public Sans", ui-sans-serif, system-ui, sans-serif;
}
```

**예시 — 녹색 테마로 변경:**

```css
@theme inline {
  --color-primary: #10b981;      /* emerald-500 */
  --color-bg-dark: #0f1a14;
  --color-panel-dark: #162320;
  --color-border-dark: #1e3a2f;
  ...
}
```

### 폰트 변경

1. `globals.css`에서 `--font-sans` 수정
2. `layout.tsx`에서 `next/font/google` import 변경

```typescript
// layout.tsx
import { Inter } from "next/font/google";
const inter = Inter({ variable: "--font-sans", subsets: ["latin"] });
```

---

## 5. UI 컴포넌트

### 5.1 사이드바

**파일**: `frontend/src/components/Sidebar.tsx`

```typescript
// 네비게이션 항목 수정
const navItems = [
  { icon: 'dashboard', label: 'Dashboard', active: true },
  { icon: 'history', label: 'Activity Logs', active: false },
  { icon: 'database', label: 'Knowledge Base', active: false },
  { icon: 'settings', label: 'Settings', active: false },
];
```

- `icon`: [Material Symbols](https://fonts.google.com/icons) 아이콘명
- `label`: 표시 텍스트
- 로고 텍스트: `InstiAgent` → 원하는 이름으로 변경 (23번 줄)

### 5.2 메타데이터 패널

**파일**: `frontend/src/components/MetadataPanel.tsx`

Processing Engine, Security Clearance, Latency 등의 표시 항목을 변경할 수 있습니다.

### 5.3 데이터 카드

**파일**: `frontend/src/components/DataCardGrid.tsx`

에이전트 응답에서 `- Label: Value` 형식의 데이터를 자동 추출하여 카드로 표시합니다. 카드 레이아웃(3열 그리드)을 변경할 수 있습니다.

---

## 6. API 연결 설정

**파일**: `frontend/src/lib/api.ts`

```typescript
// 백엔드 서버 주소 설정 (환경변수 또는 기본값)
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
```

### 환경변수로 설정하는 방법

```bash
# frontend/.env.local 파일 생성
NEXT_PUBLIC_API_URL=http://your-server:8000
```

---

## 7. 서버 실행 설정

**파일**: `run.sh`

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

| 옵션 | 설명 | 프로덕션 권장 |
|------|------|-------------|
| `--host` | 바인딩 주소 | `0.0.0.0` |
| `--port` | 포트 번호 | 필요에 따라 변경 |
| `--reload` | 코드 변경 시 자동 재시작 | 프로덕션에서는 제거 |
| `--workers` | 워커 프로세스 수 | `--workers 4` 추가 권장 |

---

## 8. MCP 서버 연동 (외부 도구 추가)

**파일**: `backend/mcp_config.json`

[MCP (Model Context Protocol)](https://modelcontextprotocol.io/)는 AI 에이전트에 외부 도구를 표준화된 방식으로 연결하는 프로토콜입니다. MCP 서버를 추가하면 에이전트가 웹 검색, 데이터베이스 접근, 파일 시스템 조작 등 다양한 외부 기능을 사용할 수 있습니다.

### 8.1 MCP 서버 추가 방법

`backend/mcp_config.json` 파일을 편집하여 MCP 서버를 추가합니다:

1. `servers` 배열에 새 서버 설정 추가
2. `"enabled": true`로 변경하여 활성화
3. 백엔드 서버 재시작

### 8.2 설정 형식

#### stdio 트랜스포트 (로컬 프로세스)

로컬에서 실행되는 MCP 서버에 사용합니다. 서버를 자식 프로세스로 실행하고 stdin/stdout으로 통신합니다.

```json
{
  "name": "my-server",
  "enabled": true,
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/allowed/path"],
  "description": "파일 시스템 접근 도구",
  "env": {
    "SOME_API_KEY": "your-key"
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | O | 서버 고유 이름 (도구 이름 접두사로 사용) |
| `enabled` | O | `true`면 서버 시작 시 연결 |
| `transport` | O | `"stdio"` |
| `command` | O | 실행할 명령어 (`npx`, `uvx`, `python` 등) |
| `args` | - | 명령어 인자 배열 |
| `description` | - | 서버 설명 (로그용) |
| `env` | - | 환경 변수 (API 키 등) |

#### SSE 트랜스포트 (원격 서버 — 레거시)

원격으로 실행 중인 MCP 서버에 HTTP SSE로 연결합니다. 기존 MCP 서버와의 호환성을 위해 지원됩니다.

```json
{
  "name": "remote-search",
  "enabled": true,
  "transport": "sse",
  "url": "http://localhost:3001/sse",
  "description": "원격 검색 API"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | O | 서버 고유 이름 |
| `enabled` | O | `true`면 서버 시작 시 연결 |
| `transport` | O | `"sse"` |
| `url` | O | SSE 엔드포인트 URL (보통 `/sse`로 끝남) |
| `description` | - | 서버 설명 |

#### Streamable HTTP 트랜스포트 (원격 서버 — 최신 권장)

MCP 최신 표준 트랜스포트입니다. 단일 HTTP 엔드포인트를 사용하며, 서버가 일반 JSON 응답 또는 SSE 스트림으로 유연하게 응답할 수 있습니다. **새로운 MCP 서버 연동 시 이 방식을 사용하세요.**

```json
{
  "name": "my-api",
  "enabled": true,
  "transport": "streamable_http",
  "url": "http://localhost:3001/mcp",
  "description": "Streamable HTTP MCP 서버"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | O | 서버 고유 이름 |
| `enabled` | O | `true`면 서버 시작 시 연결 |
| `transport` | O | `"streamable_http"` |
| `url` | O | MCP 엔드포인트 URL (보통 `/mcp`로 끝남) |
| `description` | - | 서버 설명 |

> **SSE vs Streamable HTTP**: SSE는 레거시 방식으로, 서버→클라이언트(SSE)와 클라이언트→서버(POST)에 별도 엔드포인트를 사용합니다. Streamable HTTP는 단일 엔드포인트에서 양방향 통신을 처리하며, 더 단순하고 유연합니다. 새로 연동하는 서버가 Streamable HTTP를 지원한다면 이 방식을 선택하세요.

### 8.3 예시: Brave Search 추가

1. Brave Search API 키 발급: https://brave.com/search/api/
2. MCP 서버 설치: `npm install -g @anthropic/mcp-server-brave-search`
3. `mcp_config.json` 설정:

```json
{
  "name": "brave-search",
  "enabled": true,
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@anthropic/mcp-server-brave-search"],
  "description": "Brave Search API",
  "env": {
    "BRAVE_API_KEY": "BSA-xxxxxxxxxxxxxxxx"
  }
}
```

4. 백엔드 서버 재시작

### 8.4 예시: 커스텀 MCP 서버 추가

Python으로 작성한 커스텀 MCP 서버를 연동할 수 있습니다:

```json
{
  "name": "my-custom-tool",
  "enabled": true,
  "transport": "stdio",
  "command": "python",
  "args": ["/path/to/my_mcp_server.py"],
  "description": "내부 데이터베이스 조회 도구"
}
```

### 8.5 도구 이름 규칙

MCP 서버의 도구는 `mcp__{서버이름}__{도구이름}` 형식으로 등록됩니다. 예를 들어 `brave-search` 서버의 `web_search` 도구는 `mcp__brave-search__web_search`로 등록됩니다.

### 8.6 트러블슈팅

| 증상 | 원인 및 해결 |
|------|-------------|
| 서버 시작 시 연결 실패 로그 | `command`가 설치되어 있는지 확인 (`npx`, `uvx` 등) |
| 도구가 로드되지 않음 | `"enabled": true` 확인, JSON 문법 오류 확인 |
| API 키 오류 | `env`에 올바른 키가 설정되어 있는지 확인 |
| SSE 연결 실패 | 원격 서버가 실행 중인지, URL이 올바른지 확인 (`/sse` 경로) |
| Streamable HTTP 연결 실패 | URL 경로 확인 (`/mcp`), 서버가 Streamable HTTP를 지원하는지 확인 |
| 연결은 성공하나 도구 호출 실패 | MCP 서버 로그 확인, 인자 형식이 올바른지 확인 |

> **참고**: MCP 서버 연결 실패는 다른 기능에 영향을 주지 않습니다. 실패한 서버는 건너뛰고 나머지 서버의 도구만 로드됩니다.

---

## 관리 포인트 체크리스트

### 배포 전 확인사항

- [ ] `config.py`의 `VLLM_BASE_URL`이 올바른 서버를 가리키는지 확인
- [ ] `config.py`의 `AGENT_ROOT_DIR`을 배포 경로로 변경
- [ ] `run.sh`의 `cd` 경로를 배포 경로로 변경
- [ ] `frontend/.env.local`에 `NEXT_PUBLIC_API_URL` 설정
- [ ] `AGENTS.md`의 내용이 용도에 맞는지 검토

### 운영 관리 항목

| 항목 | 빈도 | 설명 |
|------|------|------|
| vLLM 서버 상태 | 상시 | `/api/health` 엔드포인트로 확인 |
| 로그 모니터링 | 일일 | 백엔드 콘솔에서 에이전트/도구 실행 로그 확인 |
| AGENTS.md 업데이트 | 필요 시 | 에이전트 행동 패턴 개선 |
| 시스템 프롬프트 튜닝 | 주기적 | 응답 품질 기반으로 프롬프트 조정 |
| 체크포인터 백업 | 일일 | SQLite/Postgres 사용 시 DB 백업 |
| 프론트엔드 빌드 | 코드 변경 시 | `npm run build` 후 배포 |

### 성능 관련

| 설정 | 위치 | 영향 |
|------|------|------|
| `max_tokens` (오케스트레이터) | `config.py` → `get_model()` | 응답 길이 vs 응답 속도 |
| `max_tokens` (서브에이전트) | `agent.py` → `_subagent_model` | 서브에이전트 응답 길이 vs 컨텍스트 사용량 |
| `temperature` | `config.py` → `get_model()` | 창의성 vs 일관성 |
| `max_model_len` | vLLM 서버 설정 | 전체 컨텍스트 윈도우 크기 |

### 확장 가이드

| 확장 방향 | 수정 파일 | 난이도 |
|-----------|----------|--------|
| 서브에이전트 추가 | `agent.py`, `AGENTS.md` | 낮음 |
| 도구 추가 (검색, DB 등) | `agent.py` | 낮음 |
| MCP 서버 연동 (외부 도구) | `mcp_config.json` | 낮음 |
| 시스템 프롬프트 변경 | `agent.py` | 낮음 |
| 테마/브랜딩 변경 | `globals.css`, `Sidebar.tsx` | 낮음 |
| 체크포인터 교체 | `agent.py` | 중간 |
| 인증 추가 | `main.py`, 프론트엔드 | 중간 |
| 세션 관리 UI | 프론트엔드 전체 | 높음 |
| 파일 업로드 기능 | 백엔드 + 프론트엔드 | 높음 |
