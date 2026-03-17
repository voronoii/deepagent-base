# LangGraph 워크플로우 통합 계획

## Context

현재 `agent.py`는 `deepagents` 패키지의 `create_deep_agent`를 사용하여 오케스트레이터 + 서브에이전트 구조를 구성하고 있다. 내부적으로 LangGraph `CompiledStateGraph`를 반환하지만, 서브에이전트는 `task` 도구의 단순 `invoke()`로만 호출되어 그래프 수준의 워크플로우 제어(retry, 조건부 라우팅, 에스컬레이션)가 없다.

**목표**: 기존 deepagents 에이전트를 유지하면서, 상위 LangGraph StateGraph로 래핑하여 에이전트 실패 시 자동 재시도, 품질 기반 fallback, 에스컬레이션을 추가한다.

## 챗봇 수정 제안의 잔여 문제점 (추가 분석)

| # | 문제 | 설명 |
|---|------|------|
| 7 | State 전달 불일치 | `ORCHESTRATOR_AGENT.invoke(state)` 시 `AgentState`의 `error_count`, `needs_fallback` 등 deepagents가 모르는 필드를 전달 → 무시되거나 에러 |
| 8 | 초기화 순서 충돌 | `initialize_agents()` 모듈 레벨 호출 → `mcp_manager.initialize()` (async) 전에 실행되어 MCP 도구 누락 |
| 9 | 토큰 스트리밍 손실 | 노드 함수 내 `invoke()` 사용 → 내부 에이전트의 실시간 토큰 스트리밍이 외부 그래프로 전파되지 않음 |
| 10 | retry 경로 미도달 | `route_post_orchestrator`에서 `"retry"` 반환 조건 없음 (dead code) |
| 11 | Checkpointer 이중화 | 외부 그래프 + 내부 deepagents 각각 별도 `MemorySaver` → 대화 이력 분리 |

## 수정 계획 (접근법 A: agent.py 중심 최소 변경)

### 수정 파일

1. **`backend/agent.py`** — LangGraph StateGraph 래퍼 추가 (주요 변경)
2. **`backend/main.py`** — `create_orchestrator()` 반환값 변경에 따른 최소 수정 (호환성 확인)

### Phase 1: State 스키마 정의

```python
# backend/agent.py 상단
from typing import Annotated, Literal
from langchain_core.messages import BaseMessage, AIMessage, add_messages
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy, Command

class WorkflowState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # reducer 적용
    retry_count: int         # 비즈니스 레벨 재시도 횟수
    last_error: str          # 마지막 에러 정보
    fallback_used: bool      # fallback 사용 여부
```

- `add_messages` reducer: LangChain 내장, ID 기반 중복 제거 + 누적
- `retry_count`: RetryPolicy(시스템)와 별도의 비즈니스 재시도 추적

### Phase 2: 에이전트 생성 (모듈 레벨 1회)

기존 `create_orchestrator()` 구조를 유지하되, 내부에서 에이전트를 생성한 후 **StateGraph로 래핑**하여 반환.

```python
def create_orchestrator():
    """기존 방식으로 에이전트 생성 후 LangGraph 래퍼로 감싼다."""

    # === 기존 코드 유지 (에이전트 생성) ===
    model = get_model()
    research_agent_spec["tools"] = _build_research_tools()
    # ... (기존 MCP 도구 주입 코드 그대로)

    inner_agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        subagents=[research_agent_spec, report_writer_spec, risk_assessment_agent_spec],
        memory=[AGENTS_MD_PATH],
        backend=FilesystemBackend(root_dir=AGENT_ROOT_DIR),
        name="orchestrator",
        skills=[SKILLS_DIR],
        # checkpointer는 외부 그래프에서 관리 → 여기서 제거
    )

    # === 새로운 코드: StateGraph 래퍼 ===
    return _build_workflow_graph(inner_agent)
```

핵심: `checkpointer`를 내부 에이전트에서 제거하고 외부 그래프에서만 관리 (이중화 방지).

### Phase 3: 노드 함수 구현

```python
def _build_workflow_graph(inner_agent) -> CompiledStateGraph:
    """에이전트를 감싸는 워크플로우 그래프 구축."""

    # 노드 1: 메인 오케스트레이터
    def orchestrator_node(state: WorkflowState) -> dict:
        # deepagents에 필요한 키만 전달 (State 불일치 해결)
        agent_input = {"messages": state["messages"]}
        try:
            result = inner_agent.invoke(agent_input)
            return {
                "messages": result["messages"],
                "retry_count": 0,
                "last_error": "",
            }
        except Exception as e:
            return {
                "messages": [AIMessage(content=f"처리 중 오류가 발생했습니다: {e}")],
                "retry_count": state.get("retry_count", 0) + 1,
                "last_error": str(e),
            }

    # 노드 2: Fallback (개별 서브에이전트 직접 호출)
    def fallback_node(state: WorkflowState) -> dict:
        # 간단한 fallback: 연구 에이전트로 직접 처리
        sub_agent = create_deep_agent(
            model=get_model(max_tokens=2048),
            tools=_build_research_tools(),
            system_prompt=RESEARCH_AGENT_PROMPT,
        )
        agent_input = {"messages": state["messages"]}
        try:
            result = sub_agent.invoke(agent_input)
            return {
                "messages": result["messages"],
                "fallback_used": True,
                "last_error": "",
            }
        except Exception as e:
            return {
                "messages": [AIMessage(content=f"Fallback도 실패: {e}")],
                "last_error": str(e),
            }

    # 라우팅: 비즈니스 로직 실패 판단
    def route_after_orchestrator(state: WorkflowState) -> Literal["end", "fallback", "retry"]:
        retry_count = state.get("retry_count", 0)
        last_error = state.get("last_error", "")

        # 에러 없음 → 성공
        if not last_error:
            return "end"
        # 재시도 가능 (최대 2회)
        if retry_count <= 2:
            return "retry"
        # 재시도 초과 → fallback
        return "fallback"

    # 그래프 조립
    workflow = StateGraph(WorkflowState)

    workflow.add_node(
        "orchestrator",
        orchestrator_node,
        retry_policy=RetryPolicy(
            max_attempts=2,
            initial_interval=1.0,
            # transient 에러만 시스템 레벨 retry
            retry_on=lambda e: isinstance(e, (TimeoutError, ConnectionError, OSError)),
        ),
    )
    workflow.add_node("fallback", fallback_node)

    workflow.add_edge(START, "orchestrator")
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {"end": END, "fallback": "fallback", "retry": "orchestrator"},
    )
    workflow.add_edge("fallback", END)

    return workflow.compile(checkpointer=checkpointer)
```

### Phase 4: main.py 호환성 확인

`main.py`에서의 호출:
```python
_orchestrator = create_orchestrator()  # 이제 StateGraph CompiledStateGraph 반환
# 기존과 동일:
async for event in _orchestrator.astream(input_msg, config=config, stream_mode=["messages", "updates"]):
```

- `CompiledStateGraph`는 동일한 `astream` 인터페이스 지원
- `stream_mode=["messages", "updates"]`에서:
  - `"updates"` 모드: 외부 그래프의 노드 업데이트 표시 (orchestrator, fallback)
  - `"messages"` 모드: 내부 에이전트의 최종 메시지 전달
- **제한**: 내부 에이전트의 실시간 토큰 스트리밍은 `invoke()` 사용 시 손실됨

**스트리밍 손실 대안** (Phase 5로 분리):
- 내부 에이전트를 `astream()`으로 호출하고 결과를 수동 수집하면 토큰 스트리밍 복원 가능
- 또는 내부 에이전트를 subgraph 노드로 직접 등록: `workflow.add_node("orchestrator", inner_agent)`
  - 이 경우 try/except 래핑 불가 → RetryPolicy만 의존

### Phase 5: (선택적 확장) 고급 기능

향후 필요 시 추가 가능:

1. **Human-in-the-loop 에스컬레이션**:
   ```python
   from langgraph.types import interrupt
   def escalate_node(state):
       decision = interrupt({"error": state["last_error"], "message": "수동 처리 필요"})
       return {"messages": [AIMessage(content=decision)]}
   ```

2. **품질 기반 라우팅** (결과 내용 평가):
   ```python
   def quality_check(state) -> Literal["pass", "retry"]:
       last_msg = state["messages"][-1].content
       if len(last_msg) < 50 or "죄송" in last_msg:
           return "retry"
       return "pass"
   ```

3. **Send API를 이용한 병렬 에이전트 실행**:
   - 여러 서브에이전트를 동시에 실행하고 결과 취합

## 변경 요약

| 파일 | 변경 내용 | 범위 |
|------|-----------|------|
| `backend/agent.py` | `WorkflowState` 추가, `_build_workflow_graph()` 추가, `create_orchestrator()` 내부에서 래퍼 호출, checkpointer 외부 이동 | 주요 변경 |
| `backend/main.py` | 변경 없음 (CompiledStateGraph 인터페이스 호환) | 없음 |
| `backend/requirements.txt` | 변경 없음 (이미 langgraph>=1.0.0 포함) | 없음 |

## 검증 방법

1. **단위 테스트**: `create_orchestrator()` 반환값이 `CompiledStateGraph`인지 확인
2. **정상 흐름**: 메시지 전송 → orchestrator 노드 실행 → END
3. **에러 흐름**: 모델 서버 중단 → RetryPolicy 자동 재시도 확인
4. **Fallback 흐름**: retry_count 초과 → fallback 노드 실행 확인
5. **SSE 스트리밍**: `main.py`의 기존 SSE 이벤트가 정상 수신되는지 확인
6. **대화 지속성**: 동일 thread_id로 연속 대화 시 이력 유지 확인
