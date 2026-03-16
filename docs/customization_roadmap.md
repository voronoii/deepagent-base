# 커스터마이제이션 로드맵 (구현 예정)

> 컨텍스트 엔지니어링 적용 시 개발자가 쉽게 워크플로우를 커스텀할 수 있도록 만들기 위한 개선 포인트 정리.

## 현재 커스터마이제이션 구조

| 레이어 | 현재 상태 | 패턴 |
|--------|----------|------|
| 환경변수 | `MODEL_TYPE`, `VLLM_BASE_URL`, `OPENAI_API_KEY` 등 | `.env` → `config.py` |
| JSON 설정 | `mcp_config.json` (MCP 서버 선언적 등록) | 가장 깔끔한 기존 패턴 |
| 메모리 파일 | `backend/AGENTS.md` (MemoryMiddleware가 매 호출마다 읽음) | **유일한 hot-reload 포인트** |
| 프롬프트 | `agent.py` 내 Python 문자열 상수 3개 | 하드코딩 — 변경 시 코드 수정 필요 |
| 서브에이전트 | `agent.py` 내 Python dict 2개 | 하드코딩 — 추가/제거 시 코드 수정 필요 |

## 개선 포인트

### 1. 프롬프트 파일 외부화 (우선순위: 높음)

**현재**: `ORCHESTRATOR_PROMPT`, `RESEARCH_AGENT_PROMPT`, `REPORT_WRITER_PROMPT`가 `agent.py` 내 Python 문자열로 하드코딩.

**개선**: `backend/prompts/` 디렉토리에 마크다운 파일로 분리.

```
backend/prompts/
  orchestrator.md       ← ORCHESTRATOR_PROMPT 대체
  research_agent.md     ← RESEARCH_AGENT_PROMPT 대체
  report_writer.md      ← REPORT_WRITER_PROMPT 대체
```

**로딩 방식**: 서버 시작 시 파일 읽기 (AGENTS.md와 달리 hot-reload 불필요, 재시작으로 충분).

**효과**: 개발자가 Python 코드 수정 없이 마크다운 파일 편집만으로 에이전트 동작 변경 가능.

**구현 아이디어**:
```python
# config.py
PROMPTS_DIR = os.environ.get("PROMPTS_DIR", "./backend/prompts")

# agent.py
def _load_prompt(filename: str, fallback: str) -> str:
    path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("Prompt file %s not found, using inline fallback", path)
        return fallback
```

### 2. 서브에이전트 선언적 레지스트리 (우선순위: 중간)

**현재**: `research_agent_spec`, `report_writer_spec`이 `agent.py`에 하드코딩.

**개선**: `backend/agents_config.json` 추가 — `mcp_config.json` 패턴 재활용.

```json
{
  "agents": [
    {
      "name": "research-agent",
      "enabled": true,
      "description": "Research agent for investigating topics...",
      "prompt_file": "./backend/prompts/research_agent.md",
      "tools": ["duckduckgo", "mcp:*"],
      "model": {
        "max_tokens": 2048,
        "temperature": 0.1
      },
      "display": {
        "name": "리서치 에이전트",
        "action": "조사"
      }
    },
    {
      "name": "report-writer-agent",
      "enabled": true,
      "description": "Report writer agent...",
      "prompt_file": "./backend/prompts/report_writer.md",
      "tools": [],
      "model": {
        "max_tokens": 2048,
        "temperature": 0.1
      },
      "display": {
        "name": "리포트 작성 에이전트",
        "action": "작성"
      }
    }
  ]
}
```

**부가 효과**: `main.py`의 `_AGENT_DISPLAY` 하드코딩도 제거 가능 (레지스트리에서 display 정보 로드).

### 3. 출력 계약 설정 (우선순위: 중간)

**현재**: 출력 형식이 프롬프트 산문(prose) 안에 서술됨. 데이터 카드 추출 로직(`main.py`)과 프롬프트 지시가 분리되어 동기화 문제 가능.

**개선**: `backend/contracts/` 디렉토리에 구조화된 계약 정의.

```
backend/contracts/
  research_output.json   ← 리서치 에이전트 출력 스키마
  report_format.json     ← 리포트 형식 스키마
  data_cards.json        ← 데이터 카드 추출 규칙
```

**research_output.json 예시**:
```json
{
  "required_sections": ["Key Facts", "Sources", "Uncertainties"],
  "key_facts_format": "- label: value (source)",
  "max_narrative_lines": 0
}
```

**효과**: 프롬프트 지시와 추출 로직이 하나의 설정 소스를 공유하여 동기화 문제 해결.

### 4. Done Gate 설정 (우선순위: 중간)

**현재**: 완료 조건 체크 없음. LLM이 스스로 완료를 판단.

**개선 옵션 A — 프롬프트 기반** (즉시 적용 가능):
- `AGENTS.md` 또는 외부화된 `orchestrator.md`에 Done Gate 섹션 추가
- 프롬프트 지시만으로 자체 검증 루프 유도
- deepagents의 `recursion_limit: 1000`으로 재위임 가능

**개선 옵션 B — 구조화 설정** (Phase 2):
```json
// backend/contracts/done_gates.json
{
  "default": {
    "criteria": [
      "사용자 요청의 모든 요구사항이 리서치 결과에 반영됨",
      "핵심 정보가 Key Facts로 정리됨",
      "출처가 명시됨"
    ],
    "max_retries": 2,
    "failure_action": "delegate_follow_up"
  }
}
```

### 5. 환경변수 누락 보완 (우선순위: 낮음)

현재 하드코딩된 값들을 환경변수로 전환:

```python
# config.py 개선
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "dummy")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "default")
VLLM_MAX_CONTEXT_TOKENS = int(os.environ.get("VLLM_MAX_CONTEXT_TOKENS", "32768"))
OPENAI_MAX_CONTEXT_TOKENS = int(os.environ.get("OPENAI_MAX_CONTEXT_TOKENS", "128000"))
AGENTS_MD_PATH = os.environ.get("AGENTS_MD_PATH", "./backend/AGENTS.md")
MODEL_TEMPERATURE = float(os.environ.get("MODEL_TEMPERATURE", "0.1"))
ORCHESTRATOR_MAX_TOKENS = int(os.environ.get("ORCHESTRATOR_MAX_TOKENS", "4096"))
SUBAGENT_MAX_TOKENS = int(os.environ.get("SUBAGENT_MAX_TOKENS", "2048"))
```

### 6. Checkpointer 설정 (우선순위: 낮음)

```python
# config.py
CHECKPOINTER_TYPE = os.environ.get("CHECKPOINTER_TYPE", "memory")  # memory | sqlite | postgres
CHECKPOINTER_DSN = os.environ.get("CHECKPOINTER_DSN", "")
```

### 7. ExecutionState 구조화 (우선순위: 높음, 설계 필요)

**현재**: `schemas.py`에 API 레벨 스키마만 존재.

**개선**: deepagents의 `context_schema` 파라미터를 활용하여 에이전트 실행 상태를 구조화.

```python
class ExecutionState(TypedDict):
    goal: str
    constraints: list[str]
    done_criteria: list[str]
    findings: list[Finding]
    open_questions: list[str]
```

**핵심 고려사항**: SubAgentMiddleware가 `_EXCLUDED_STATE_KEYS = {"messages", "todos", "structured_response"}`만 필터링하므로, `context_schema`로 추가한 커스텀 필드는 서브에이전트에 자동 전달됨. 이 특성을 활용하면 orchestrator → research-agent → report-writer 간 구조화된 상태 공유 가능.

**설계 필요 사항**:
- `context_schema`에 ExecutionState를 넣을 때 reducer 정의 (append vs replace)
- 서브에이전트가 ExecutionState를 업데이트하는 방법
- 프롬프트에서 ExecutionState 필드를 참조하는 패턴

## 구현 권장 순서

| Phase | 작업 | 파일 |
|-------|------|------|
| Phase 1 (현재) | 프롬프트 내 계약 추가 + 도구 일관화 | `agent.py`, `AGENTS.md` |
| Phase 2 | 프롬프트 파일 외부화 | `backend/prompts/`, `agent.py`, `config.py` |
| Phase 3 | 서브에이전트 레지스트리 | `agents_config.json`, `agent.py`, `main.py` |
| Phase 4 | ExecutionState + context_schema | `schemas.py`, `agent.py` |
| Phase 5 | 출력 계약/Done Gate 구조화 | `backend/contracts/` |
| Phase 6 | 환경변수 보완 | `config.py` |
