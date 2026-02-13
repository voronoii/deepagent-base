# DeepAgent-Base 프로젝트 로그

## 1. 작업한 내용과 완료된 사항

### 1.1 백엔드 (FastAPI + deepagents)
| 작업 | 상태 | 설명 |
|------|------|------|
| FastAPI 서버 구축 | 완료 | SSE 스트리밍 기반 `/api/chat` 엔드포인트 |
| 멀티 에이전트 워크플로우 | 완료 | Orchestrator + Research Agent + Report Writer (deepagents 프레임워크) |
| Sub-agent 컨텍스트 오버플로우 수정 | 완료 | Sub-agent 전용 모델(`max_tokens=2048`) 분리 |
| SSE 파서 버그 수정 | 완료 | `currentEvent`/`currentData` 스코프 문제, `\r` 처리 추가 |
| 구조화된 로깅 | 완료 | 에이전트/도구 호출 추적, 타이밍 정보 기록 |
| Fallback 메커니즘 | 완료 | 에러 시 중간 결과(`fallback_text`)라도 사용자에게 전달 |
| MCP 통합 | 완료 | stdio, SSE, Streamable HTTP 3가지 transport 지원 |
| 토큰 사용량 추적 | 완료 | AIMessage에서 `response_metadata.token_usage` 추출, `metadata` SSE 이벤트로 전송 |
| MCP 서버 디렉토리 분리 | 완료 | `mcp_servers/` 최상위 디렉토리로 독립 — Docker 서비스 단위 분리 대비 |
| MCP 일괄 실행 런처 | 완료 | `mcp_servers/run_all.sh` — nohup + disown으로 터미널 종료 후에도 프로세스 유지, 서버별 로그 파일 |
| MCP Health Check API | 완료 | `GET /api/mcp/health` — 각 서버 상태(online/offline/error), 레이턴시, 등록된 도구 목록 반환 |
| MCP Health Dashboard | 완료 | `GET /mcp/dashboard` — 다크 테마 웹 대시보드, 10초 자동 갱신, 상태 요약 카드 |
| MCP 도구 정보 오케스트레이터 주입 | 완료 | `_build_mcp_tools_description()`으로 서버 시작 시 MCP 도구 목록을 프롬프트에 동적 추가 |
| Docker Compose 기본 구성 | 완료 | `docker-compose.yml` — backend, frontend, mcp-news 서비스 정의, `DOCKER_ENV` 기반 URL 자동 전환 |
| 에이전트별 토큰 추적 로깅 | 완료 | `_extract_token_usage()`에 `source` 파라미터 추가, 에이전트별 토큰 변화 + 피크/경고 로깅 |
| 컨텍스트 자동 요약 활성화 | 완료 | `model.profile` 설정으로 deepagents `SummarizationMiddleware` 올바른 임계값(85%/10%) 적용 |
| config.py 환경변수화 | 완료 | `VLLM_BASE_URL`, `AGENT_ROOT_DIR`을 `os.environ.get()`으로 변경, Docker 환경 대응 |
| Backend Dockerfile | 완료 | `python:3.11-slim` 기반, `from backend.xxx` import 구조 유지를 위해 `/app/backend/`에 복사 |
| Backend requirements.txt | 완료 | deepagents, langchain-*, fastapi, mcp 등 최소 의존성 명시 |
| Docker Compose 완성 | 완료 | health check, `restart: unless-stopped`, `depends_on condition`, 포트 통일(1879) |
| .env.example | 완료 | 팀원 온보딩용 환경변수 템플릿 (`VLLM_BASE_URL`, `NEXT_PUBLIC_API_URL`) |

### 1.2 프론트엔드 (Next.js 16 + Tailwind v4)
| 작업 | 상태 | 설명 |
|------|------|------|
| 채팅 UI 구축 | 완료 | Sidebar + ChatArea + ReasoningPanel 3단 레이아웃 |
| Hydration 에러 수정 | 완료 | `suppressHydrationWarning` 적용 |
| `crypto.randomUUID` 폴백 | 완료 | HTTP 환경용 Math.random 기반 UUID 생성 함수 |
| 마크다운 렌더링 | 완료 | `react-markdown` + `remark-gfm` + `@tailwindcss/typography` |
| 접이식 에이전트 스텝 UI | 완료 | `CollapsibleSteps` 컴포넌트 (자동 열기/닫기, 타임라인 UI) |
| 실시간 추론 과정 표시 | 완료 | 로딩 중 라이브 스텝 + 완료 후 메시지에 임베드 |
| 채팅 영역 너비 확장 | 완료 | `max-w-3xl`(48rem) → `max-w-[62rem]` (약 130%) |
| 토큰 사용량 인디케이터 | 완료 | 입력창 하단 좌측에 프로그레스 바 + 수치 표시 |
| Next.js standalone 빌드 | 완료 | `next.config.ts`에 `output: "standalone"` 추가, Docker 이미지 최소화 |
| Frontend Dockerfile | 완료 | multi-stage 빌드 (deps → builder → runner), `NEXT_PUBLIC_API_URL` ARG 전달 |

### 1.3 문서 및 도구
| 작업 | 상태 | 설명 |
|------|------|------|
| CUSTOMIZATION_GUIDE.md | 완료 | LLM, 에이전트, 프롬프트, 테마, MCP 등 커스텀 가이드 |
| 뉴스 MCP 툴 Streamable HTTP 전환 | 완료 | `get_news_tool.py` transport 변경 |
| MCP 도구 템플릿 | 완료 | `mcp_servers/_template/` — 새 MCP 도구 생성 시 복사용 보일러플레이트 |

---

## 2. 성공한 것과 실패한 것

### 성공

**SSE 파서 데이터 유실 버그 해결**
- 증상: 에이전트 응답이 간헐적으로 누락
- 원인: `while(true)` 루프 안에서 `currentEvent`/`currentData`가 매 `read()` 호출마다 초기화됨. 이벤트가 여러 chunk에 걸쳐 도착할 때 데이터 손실 발생
- 해결: 변수를 루프 밖으로 이동, `\r` 문자 처리 추가, 스트림 종료 시 잔여 이벤트 처리 로직 추가

**Sub-agent 500 에러 해결**
- 증상: 단순 인사에는 응답이 오지만, 하위 에이전트/도구가 필요한 질의에서 vLLM 500 에러 ("Unexpected token 173781")
- 원인: Sub-agent 응답이 길어져 32k 컨텍스트 윈도우 초과
- 해결: Sub-agent 전용 모델 인스턴스(`max_tokens=2048`) 분리 + `fallback_text` 메커니즘으로 부분 결과 보존

**MCP 멀티 트랜스포트 통합**
- stdio, SSE, Streamable HTTP 3가지 모두 지원하는 `MCPToolManager` 구현
- LangChain `StructuredTool`로 자동 래핑하여 에이전트에서 바로 사용 가능
- 서버 연결 실패 시에도 다른 기능에 영향 없는 graceful degradation

**MCP 서버 독립 디렉토리 구조화**
- `mcp_servers/` 최상위 디렉토리로 분리하여 Docker 컨테이너화 대비
- 공통 Dockerfile (`ARG TOOL_DIR`)로 MCP 서버별 이미지 빌드
- `run_all.sh`로 로컬 개발 시 일괄 실행/중지 (nohup + disown + PID 관리 + 로그)
- 뉴스 MCP 도구를 외부 경로(`spatial/`)에서 `mcp_servers/news/`로 이전

**MCP Health Check 대시보드**
- `MCPToolManager.check_health()`로 연결된 세션은 `list_tools()` 호출, 미연결 서버는 TCP probe
- `GET /api/mcp/health` JSON API + `GET /mcp/dashboard` 웹 대시보드
- 다크 테마, 상태 요약 카드(Online/Offline/Total), 등록된 도구 칩, 10초 자동 갱신

**MCP 도구 정보 오케스트레이터 프롬프트 주입**
- 기존 문제: MCP 도구가 research-agent에 주입되지만, 오케스트레이터가 존재를 모름
- `_build_mcp_tools_description()`으로 `create_orchestrator()` 시점에 도구 목록을 동적으로 프롬프트에 추가
- 새 MCP 도구 추가 시 서버 재시작만으로 자동 반영

**컨텍스트 자동 요약(SummarizationMiddleware) 활성화 — 상세**

deepagents 프레임워크에는 `SummarizationMiddleware`가 내장되어 있으며, `create_deep_agent()` 호출 시 자동으로 미들웨어 스택에 포함된다. 이 미들웨어는 매 LLM 호출 전(`abefore_model`)에 실행되어 컨텍스트 윈도우 초과를 방지한다.

**발견된 문제:**
- deepagents `graph.py:144-162`에서 `model.profile["max_input_tokens"]` 존재 여부에 따라 요약 임계값을 결정
- `ChatOpenAI` (vLLM)의 `model.profile`은 기본적으로 빈 딕셔너리 `{}`
- 따라서 fallback 경로로 빠져서 `trigger=("tokens", 170000)` 적용
- 우리 vLLM 컨텍스트 윈도우는 32,768 토큰 → **170k에 도달하기 전에 500 에러 발생**
- 즉, SummarizationMiddleware가 존재하지만 **사실상 비활성 상태**였음

**해결:**
- `config.py`의 `get_model()`에서 `model.profile = {"max_input_tokens": MAX_CONTEXT_TOKENS}` 설정
- deepagents가 이제 올바른 임계값을 자동 계산:

```
profile 있을 때 (수정 후):
  trigger = ("fraction", 0.85)  → 32768 * 0.85 = 27,852 토큰에서 요약 발동
  keep = ("fraction", 0.10)     → 32768 * 0.10 = 3,276 토큰의 최근 메시지만 유지
  truncate_args: 85%에서 write_file/edit_file의 긴 인자 잘라냄

profile 없을 때 (수정 전 — 문제 상태):
  trigger = ("tokens", 170000)  → 32k 윈도우에서 절대 도달 불가
  keep = ("messages", 6)        → 최근 6개 메시지
  → 요약이 발동하지 않아 대화가 길어지면 500 에러 발생
```

**SummarizationMiddleware 동작 흐름 (수정 후):**
```
매 LLM 호출 전 abefore_model() 실행
  │
  ├─ Step 1: truncate_args 체크
  │   └─ 85% 초과 시 오래된 메시지의 write_file/edit_file 인자 잘라냄
  │
  ├─ Step 2: summarization 체크
  │   └─ 85% (27,852 토큰) 초과 여부 확인
  │
  ├─ 미초과 → 그대로 진행
  │
  └─ 초과 시 → 요약 발동
       ├─ 1. 오래된 메시지를 /conversation_history/{thread_id}.md에 백업
       ├─ 2. LLM으로 요약(summary) 생성
       ├─ 3. 원본 메시지 제거 (RemoveMessage + REMOVE_ALL_MESSAGES)
       └─ 4. [요약 HumanMessage + 최근 3,276 토큰분 메시지]로 교체
            └─ 요약 메시지에 백업 파일 경로 포함 → 에이전트가 필요시 원본 참조 가능
```

**에이전트별 토큰 추적 로깅:**
- 기존: 오케스트레이터/서브에이전트의 토큰 수가 구분 없이 프론트엔드에 전달 → 줄었다 늘었다 혼란
- 수정: `_extract_token_usage(msg, source=node_name)`으로 어떤 에이전트의 토큰인지 `source` 필드 추가
- 백엔드 로그에 에이전트별 컨텍스트 변화, 피크 사용량, 80% 초과 경고 기록:
```
INFO  Token usage [orchestrator]: prompt=8200, completion=150, total=8350 (25% of 32768)
INFO  Context change [orchestrator]: 0 → 8200 (+8200 tokens)
INFO  Token usage [research-agent]: prompt=1200, completion=500, total=1700 (4% of 32768)
INFO  Context change [research-agent]: 8200 → 1200 (-7000 tokens)
INFO  Context summary — peak_prompt_tokens=8200 (25% of 32768), final_prompt_tokens=6500
WARNING  Context usage HIGH (85%) — consider conversation history trimming for thread=abc123
```

**Docker 컨테이너화 완료**
- Backend: `python:3.11-slim` 기반, `from backend.xxx` import 구조 유지를 위해 소스를 `/app/backend/`에 복사하는 패턴 적용
- Frontend: multi-stage 빌드(deps → builder → runner)로 이미지 크기 최소화, `output: "standalone"` 활성화
- MCP: 기존 공통 Dockerfile 유지, `EXPOSE` 하드코딩 제거하여 포트를 환경변수에 위임
- docker-compose: health check + `depends_on condition`으로 시작 순서 보장 (mcp-news → backend → frontend)
- `config.py` 환경변수화: `VLLM_BASE_URL`, `AGENT_ROOT_DIR`을 `os.environ.get()`으로 변경하여 Docker/로컬 양쪽 지원
- `.env.example`로 팀원 온보딩 간소화: `cp .env.example .env && docker compose up --build`

### 실패/미완료

**vLLM 토큰 사용량 반환 미확인**
- `_extract_token_usage()`를 구현했으나, 실제 vLLM 서버가 `response_metadata.token_usage`를 반환하는지 실서버에서 검증하지 못함
- vLLM 버전에 따라 `usage` 필드가 비어있을 수 있음. 이 경우 UI에 `— / —`으로 표시됨
- 대안: vLLM `--enable-usage-stats` 옵션 또는 tiktoken 기반 클라이언트 측 추정

**Streamable HTTP 런처** → 완료 (`mcp_servers/run_all.sh`로 해결)

---

## 3. 주요 결정 사항과 그 이유

| 결정 | 이유 |
|------|------|
| **Sub-agent 별도 모델 인스턴스** (`max_tokens=2048`) | 하나의 모델로 공유하면 sub-agent 응답이 길어질 때 orchestrator의 컨텍스트 윈도우(32k)를 초과. 분리하여 각 sub-agent의 응답 길이를 제한 |
| **`fallback_text` 메커니즘** | 에러 발생 시에도 중간까지 생성된 orchestrator 사고 과정을 사용자에게 제공. 완전한 실패보다 부분 결과가 사용자 경험에 유리 |
| **SSE `stream_mode="updates"`** | LangGraph의 `updates` 모드가 노드별 상태 변화를 구조적으로 전달. `values` 모드보다 세밀한 단계별 추적 가능 |
| **MCP 설정을 별도 JSON 파일로** | `mcp_config.json`으로 분리하여 팀원이 코드 수정 없이 MCP 서버 추가/제거 가능. 배포 환경별 설정 관리 용이 |
| **Streamable HTTP 지원 추가** | SSE는 단방향(서버→클라이언트)이고 `/sse` + `/messages/` 이중 엔드포인트 필요. Streamable HTTP는 단일 `/mcp/` 엔드포인트에서 양방향 통신으로 더 단순하고 MCP 표준 권장 방식 |
| **토큰 사용량을 `metadata` SSE 이벤트로** | 기존 `reasoning_step`/`message` 이벤트와 분리하여 관심사 분리. UI에서 선택적으로 처리 가능 |
| **Tailwind v4 `@theme inline` + `@plugin`** | Next.js 16 + Tailwind v4 조합에서 `tailwind.config.js` 대신 CSS 내 `@theme` 블록 사용이 표준. `@tailwindcss/typography`도 `@plugin` 지시어로 로드 |
| **`MAX_CONTEXT_TOKENS`를 config.py에** | 하드코딩 대신 설정 파일에 배치하여 vLLM 서버 변경 시 한 곳만 수정 |
| **MCP 서버를 `mcp_servers/` 최상위 디렉토리로 분리** | MCP 서버는 독립 프로세스이므로 backend 내부에 두면 Docker 서비스 분리 어려움. 최상위에 두면 서비스별 컨테이너, 독립 의존성, 개별 재시작 가능 |
| **`url_docker` 필드 + `DOCKER_ENV` 환경변수** | 하나의 `mcp_config.json`으로 로컬(`localhost`)과 Docker(`컨테이너명`) 환경 모두 지원. 설정 파일 이중화 방지 |
| **MCP 도구 목록을 오케스트레이터 프롬프트에 동적 주입** | 오케스트레이터가 MCP 도구 존재를 몰라서 활용하지 못하는 문제 해결. 서버 시작 시 자동 생성하여 새 도구 추가 시 코드 수정 불필요 |
| **`nohup` + `disown` 런처 패턴** | 단순 `&` 백그라운드는 터미널 종료 시 SIGHUP으로 프로세스 종료됨. nohup+disown으로 터미널 독립 실행 보장 |
| **`model.profile` 수동 설정** | vLLM의 `ChatOpenAI`는 `profile`이 빈 딕셔너리. deepagents가 170k fallback 사용 → 32k 윈도우에서 무의미. `{"max_input_tokens": 32768}` 설정으로 85%/10% 자동 요약 활성화 |
| **토큰 추적에 `source` 필드 추가** | 오케스트레이터(큰 컨텍스트)와 서브에이전트(작은 컨텍스트)의 토큰이 구분 없이 표시되면 사용자가 컨텍스트 압축으로 오해. `source` 필드로 어떤 에이전트의 토큰인지 명시 |
| **Backend Dockerfile에서 `/app/backend/`에 복사** | `from backend.config import ...` 형태의 패키지 import를 유지하기 위해 `COPY . ./backend/` + `WORKDIR /app`에서 uvicorn 실행 |
| **Frontend multi-stage 빌드 + standalone** | deps/builder/runner 3단계로 최종 이미지에 `node_modules` 미포함. `output: "standalone"`으로 Next.js가 필요한 파일만 `.next/standalone`에 추출 |
| **`NEXT_PUBLIC_API_URL`을 Docker ARG로 전달** | Next.js의 `NEXT_PUBLIC_*`는 빌드타임에 번들에 삽입됨. 런타임 환경변수가 아니므로 `docker compose build` 시 ARG로 전달 필요 |
| **MCP Dockerfile에서 `EXPOSE` 제거** | 각 MCP 서버마다 포트가 다를 수 있으므로 하드코딩 대신 `MCP_PORT` 환경변수에 위임. docker-compose의 `ports` 매핑으로 제어 |
| **`depends_on` + `condition: service_healthy`** | 단순 `depends_on`은 컨테이너 시작만 보장. health check 통과 후 의존 서비스 시작으로 연결 실패 방지 |

---

## 4. 배운 교훈과 주의사항

### SSE 스트리밍
- **청크 경계를 신뢰하지 말 것**: TCP 패킷 분할로 하나의 SSE 이벤트가 여러 `read()` 호출에 걸쳐 도착할 수 있음. 상태 변수를 반드시 루프 바깥에 유지
- **`\r\n` vs `\n`**: SSE 표준은 `\r\n`을 사용하지만 일부 서버는 `\n`만 전송. 양쪽 모두 처리 필요
- **`done` 이벤트 보장**: 스트림이 비정상 종료될 수 있으므로 `doneEmitted` 플래그로 추적하고, 미수신 시 클라이언트에서 강제 호출

### vLLM 컨텍스트 관리
- **32k 컨텍스트는 생각보다 빨리 소진됨**: Orchestrator 프롬프트 + 대화 이력 + sub-agent 응답이 누적되면 금방 한계에 도달
- **`max_tokens`는 출력 제한이지 입력 제한이 아님**: 입력(prompt_tokens) + 출력(completion_tokens)의 합이 `max_model_len`을 초과하면 500 에러 발생
- **에러 메시지 해석**: "Unexpected token 173781"은 토큰 ID가 vocabulary 범위를 초과했다는 의미가 아니라, 컨텍스트 위치 173781이 max_model_len을 초과했다는 의미

### Next.js + Tailwind v4
- **Hydration 불일치**: 브라우저 확장 프로그램이 `<html>` 태그를 수정하면 hydration 에러 발생. `suppressHydrationWarning`으로 해결
- **`crypto.randomUUID`**: HTTPS가 아닌 환경(HTTP localhost)에서는 사용 불가. 폴백 필수
- **Tailwind v4**: `tailwind.config.js` 대신 CSS의 `@theme`, `@plugin` 사용. 플러그인은 `@plugin "@tailwindcss/typography"` 형태로 로드

### deepagents 컨텍스트 엔지니어링
- **`model.profile`이 핵심**: deepagents의 `SummarizationMiddleware`는 `model.profile["max_input_tokens"]` 존재 여부로 요약 전략을 결정. OpenAI/Anthropic 공식 모델은 자동 설정되지만, vLLM 등 커스텀 모델은 반드시 수동 설정 필요
- **미들웨어 스택 순서**: `create_deep_agent()`가 자동으로 `[TodoList → Filesystem → SubAgent → Summarization → PromptCaching → PatchToolCalls]` 미들웨어 스택 구성. 추가 미들웨어는 이 뒤에 붙음
- **요약 메시지 구조**: 요약 시 `HumanMessage(additional_kwargs={"lc_source": "summarization"})`로 표시. 내용에 백업 파일 경로 포함 → 에이전트가 `read_file`로 원본 참조 가능
- **`truncate_args`와 `summarization`은 별도 단계**: 같은 미들웨어 안에서 순차 실행. truncate_args는 오래된 메시지의 `write_file`/`edit_file` 인자만 잘라냄 (코드 내용이 길어지는 것 방지)
- **대화 이력 백업 경로**: `/conversation_history/{thread_id}.md` — `FilesystemBackend`의 `root_dir` 기준. 각 요약 이벤트마다 타임스탬프와 함께 append
- **fraction vs tokens vs messages**: trigger/keep 설정에 3가지 단위 지원. `("fraction", 0.85)`는 모델 프로필 의존, `("tokens", N)`은 절대값, `("messages", N)`은 메시지 수 기준

### Docker 컨테이너화
- **패키지 import 구조와 Dockerfile의 관계**: `from backend.config import ...` 형태의 import를 사용하면 Dockerfile에서 `COPY . ./backend/`로 서브디렉토리에 복사하고 `WORKDIR /app`에서 실행해야 함. 단순히 `COPY . .`로 하면 `ModuleNotFoundError: No module named 'backend'` 발생
- **Next.js `NEXT_PUBLIC_*`는 빌드타임 변수**: 런타임에 `process.env`로 읽는 것처럼 보이지만, 실제로는 `next build` 시점에 번들에 하드코딩됨. Docker에서는 반드시 `ARG`로 빌드 시 전달해야 함. 런타임 환경변수로는 변경 불가
- **`output: "standalone"`의 효과**: Next.js가 `.next/standalone/`에 `node_modules`의 필요한 부분만 추출하여 `server.js`로 실행 가능. Docker 이미지에 전체 `node_modules`를 복사할 필요 없음 → 이미지 크기 대폭 감소 (207MB)
- **health check의 `start_period`**: FastAPI + deepagents 에이전트 초기화에 시간이 걸리므로 `start_period: 30s`로 설정. 이 기간 동안 health check 실패는 무시됨. 너무 짧으면 컨테이너가 unhealthy로 판정되어 의존 서비스가 시작되지 않음
- **`depends_on condition`과 단순 `depends_on`의 차이**: `depends_on: [mcp-news]`는 컨테이너가 "시작"만 되면 진행. `condition: service_healthy`는 health check를 통과해야 진행. MCP 서버가 준비되기 전에 backend가 연결을 시도하면 실패하므로 반드시 `service_healthy` 사용
- **빌드된 이미지 크기 참고**: backend 450MB (Python + ML 라이브러리), frontend 207MB (standalone), mcp-news 186MB (Python + requests)

### MCP 통합
- **FastMCP transport 환경변수**: `FASTMCP_SERVER_HOST`, `FASTMCP_SERVER_PORT` (SSE) vs `FASTMCP_HOST`, `FASTMCP_PORT` (일반). 버전에 따라 다를 수 있음
- **Streamable HTTP 기본 경로**: `/mcp/` (끝에 슬래시 포함)
- **`streamablehttp_client` 반환값**: SSE는 `(read, write)` 2개, Streamable HTTP는 `(read, write, _)` 3개 반환. 세 번째 값 무시 필요

---

## 5. 다음 단계

### 즉시 필요
1. **vLLM 토큰 사용량 검증**: 실서버에서 `response_metadata.token_usage`가 실제로 반환되는지 확인. 미반환 시 tiktoken 기반 클라이언트 추정 방식 검토
2. ~~**Streamable HTTP 런처 작성**~~ → 완료 (`mcp_servers/run_all.sh`)

### 예정된 작업
3. ~~**MCP Health Check 웹페이지**~~ → 완료 (`/mcp/dashboard` + `/api/mcp/health`)
   - ~~각 MCP 서버 상태 (online/offline/error)~~ ✅
   - ~~Health check 엔드포인트 주기적 폴링~~ ✅
   - 서버 시작/중지/재시작 제어 (대시보드에서 직접 제어 — 미구현)
   - ~~등록된 도구 목록 조회~~ ✅
4. **추가 MCP 도구 개발**: `mcp_servers/_template/` 기반으로 새 도구 추가
5. ~~**Docker 컨테이너화**~~ → 완료 (backend/frontend/MCP 서버 Dockerfile + docker-compose.yml + .env.example)

### 개선 사항
6. ~~**대화 이력 관리**~~ → 완료 (deepagents `SummarizationMiddleware` + `model.profile` 설정으로 자동 요약/압축 활성화)
7. **에러 복구 강화**: SSE 연결 끊김 시 자동 재연결
8. **프론트엔드 테마 커스텀**: CUSTOMIZATION_GUIDE.md 기반으로 팀원별 테마 적용 기능
9. **MCP 대시보드 서버 제어**: 대시보드에서 MCP 서버 시작/중지/재시작 버튼 추가

---

## 6. 중요 파일 맵

```
DeepAgent-Base/
├── backend/
│   ├── Dockerfile             # Backend Docker 이미지 (python:3.11-slim)
│   ├── requirements.txt       # Python 의존성 (deepagents, langchain, fastapi 등)
│   ├── .dockerignore          # Docker 빌드 제외 파일
│   ├── config.py              # vLLM 연결 설정, MAX_CONTEXT_TOKENS, model.profile 설정 (환경변수 대응)
│   ├── agent.py               # 멀티 에이전트 워크플로우 정의
│   │                            - ORCHESTRATOR_PROMPT, RESEARCH_AGENT_PROMPT, REPORT_WRITER_PROMPT
│   │                            - create_orchestrator() → StateGraph
│   │                            - _subagent_model (max_tokens=2048)
│   │                            - _build_mcp_tools_description() → MCP 도구 정보 프롬프트 주입
│   ├── main.py                # FastAPI 앱 + SSE 스트리밍
│   │                            - _stream_agent_response() → SSE 이벤트 생성
│   │                            - _extract_token_usage() → 토큰 메타데이터
│   │                            - POST /api/chat, GET /api/health
│   │                            - GET /api/mcp/health → MCP 서버 헬스체크 API
│   │                            - GET /mcp/dashboard → MCP 헬스체크 대시보드
│   ├── schemas.py             # Pydantic 모델 (ChatRequest 등)
│   ├── mcp_config.json        # MCP 서버 설정 (url + url_docker 이중 구성)
│   ├── mcp_tools.py           # MCPToolManager (stdio/SSE/Streamable HTTP)
│   │                            - check_health() → 서버별 상태/레이턴시/도구 목록
│   │                            - DOCKER_ENV 환경변수로 url_docker 자동 전환
│   └── AGENTS.md              # 에이전트 시스템 프롬프트 원본
│
├── mcp_servers/               # MCP 서버 모음 (독립 프로세스)
│   ├── Dockerfile             # 공통 Dockerfile (ARG TOOL_DIR로 서버 선택)
│   ├── run_all.sh             # 일괄 실행/중지 (nohup + disown + PID 관리)
│   ├── logs/                  # 서버별 로그 파일 (자동 생성)
│   ├── news/
│   │   ├── server.py          # 부동산 뉴스 검색 MCP (포트 1879)
│   │   └── requirements.txt
│   └── _template/             # 새 MCP 도구 생성용 보일러플레이트
│       ├── server.py
│       └── requirements.txt
│
├── frontend/
│   ├── Dockerfile             # Frontend Docker 이미지 (multi-stage, node:20-alpine)
│   ├── .dockerignore          # Docker 빌드 제외 파일
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx     # 루트 레이아웃 (suppressHydrationWarning)
│   │   │   ├── page.tsx       # 메인 페이지 (상태 관리 허브)
│   │   │   └── globals.css    # Tailwind v4 테마 (@theme, @plugin)
│   │   ├── components/
│   │   │   ├── ChatArea.tsx       # 채팅 영역 (메시지 리스트 + 라이브 스텝)
│   │   │   ├── ChatInput.tsx      # 입력창 + 토큰 사용량 인디케이터
│   │   │   ├── AssistantMessage.tsx # 어시스턴트 메시지 (마크다운 + 데이터카드)
│   │   │   ├── UserMessage.tsx    # 사용자 메시지
│   │   │   ├── CollapsibleSteps.tsx # 접이식 에이전트 스텝 타임라인
│   │   │   ├── Sidebar.tsx        # 좌측 사이드바
│   │   │   ├── TopNav.tsx         # 상단 네비게이션
│   │   │   ├── ReasoningPanel.tsx # 우측 추론 과정 패널
│   │   │   └── DataCardGrid.tsx   # 데이터 카드 그리드
│   │   ├── lib/
│   │   │   └── api.ts            # SSE 클라이언트 (sendMessage, processSSEEvent)
│   │   └── types/
│   │       └── index.ts          # TypeScript 타입 정의
│   ├── package.json
│   └── next.config.ts
│
├── docker-compose.yml         # Docker 오케스트레이션 (health check, restart, 시작 순서 보장)
├── .env.example               # 팀원 온보딩용 환경변수 템플릿
├── CUSTOMIZATION_GUIDE.md     # 팀 배포용 커스텀 가이드
└── PROJECT_LOG.md             # 이 문서
```

### SSE 이벤트 흐름도

```
[사용자 입력]
    │
    ▼
POST /api/chat
    │
    ▼
_stream_agent_response()
    │
    ├──► reasoning_step  (도구 호출 시작)     → CollapsibleSteps UI 업데이트
    ├──► metadata        (토큰 사용량)         → ChatInput 인디케이터 업데이트
    ├──► reasoning_step  (도구 호출 완료)     → CollapsibleSteps 상태 변경
    ├──► metadata        (토큰 사용량 갱신)    → ChatInput 인디케이터 업데이트
    ├──► message         (최종 응답)           → AssistantMessage 렌더링
    └──► done            (스트림 종료)         → isLoading = false
```
