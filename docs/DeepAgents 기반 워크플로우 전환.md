## Deep Agents를 사용하는 이유

### 기존 시스템의 문제점

**1. 컨텍스트 관리의 한계**

- 에이전트가 참고해야 하는 모든 내용을 시스템 프롬프트에 직접 주입하는 구조
- 기본 시스템 프롬프트가 이미 길고, chat history와 tool output이 누적되면서 전체 컨텍스트가 과도하게 비대해짐
- 메모리가 token_limit 초과 시 오래된 메시지를 단순 삭제하는 방식이라, 대화가 길어질수록 초반 컨텍스트가 유실됨

**2. 프레임워크 한계 우회를 위한 코드 누적**

- LlamaIndex의 AgentWorkflow는 실행할 때마다 Context가 초기화되는 구조여서, 현재 라우팅된 에이전트 정보 등을 유지하기 위해 세션 내내 보관되는 별도의 컨텍스트 저장 클래스를 직접 만들어야 했음
- 또한 매 턴 끝마다 현재 에이전트를 수동으로 메인 에이전트로 리셋하는 코드가 필요했음

**3. 에이전트 간 흐름 제어의 한계**

- handoff를 통해 에이전트 간 제어권이 수평으로 이전되며, 한번 넘어간 제어권이 자동으로 돌아오지 않음
- 에이전트 체인이 길어질수록 흐름 추적과 결과 취합이 어려워짐

---

### Deep Agents 가 해결하는 것

**미들웨어 아키텍처**: LangGraph 상태 관리 + **미들웨어 훅**(before_model, wrap_tool_call 등)으로 에이전트 루프 각 단계에 **코드 기반 후처리/검증** 주입.

미들웨어에 의해 아래 도구들이 기본적으로 제공됨

TodoListMiddleware(write_todos), FilesystemMiddleware(ls, read_file, write_file, edit_file), SubAgentMiddleware(task) 등

(아래문단은 자세한 버전으로 추후 삭제예정)

Deep Agents는 미들웨어 아키텍처를 통해 에이전트 루프의 각 단계(모델 호출 전/후, 도구 호출 전/후)에
코드로 정의된 고정 로직을 주입할 수 있는 구조를 제공한다.
내부적으로 LangGraph 기반 상태 관리를 사용하면서도, 사용자는 선택적으로
미들웨어 기반(빠른 구성) 또는 커스텀 LangGraph(복잡한 로직) 중 선택할 수 있어,
기존 시스템의 문제점들을 구조적으로 해결

### 기존 문제에 대응하는 해결

**컨텍스트 관리 → MemoryMiddleware + SummarizationMiddleware**

- **AGENTS.md 기반 프로젝트 메모리**: 에이전트 초기화 시 AGENTS.md의 위치와 사용 지침이 프롬프트에 추가되며, 실제 내용은 `read_file` 도구로 필요 시 동적으로 참조함. 시스템 프롬프트에 전체 내용을 하드코딩하지 않으므로 컨텍스트 부담이 줄어듦.
- **자동 오프로딩**: 모든 tool 결과와 history가 20k 토큰이 초과될 때 자동으로 파일 저장,  경로+미리보기만 prompt에 유지
- **자동 요약**: 전체 message history가 모델 context window의 85%를 초과하면 `SummarizationMiddleware`가 이전 메시지를 LLM으로 요약하고 최근 10%만 유지. 원본은 filesystem에 보관됨

**LangGraph Checkpointer**

- 기본 checkpointer(MemorySaver 등)가 thread_id 기반으로 상태 자동 저장/복원
- Context를 외부에서 별도로 관리하거나, 에이전트를 수동으로 리셋하는 과정이 불필요

**흐름 제어 → 서브에이전트 오케스트레이션**

- **메인 에이전트**가 `task` 도구로 서브에이전트에 작업을 위임하되, 결과를 자동 수렴하여 흐름이 명시적임
- 각 서브에이전트는 격리된 컨텍스트에서 실행되므로, 서로 다른 하위 작업의 대화 히스토리가 오염되지 않는다.
- 서브에이전트별로 모델, 도구, 미들웨어를 독립적으로 설정할 수 있다.

### 관련 추가 내용

**기본 도구 자동 제공**

미들웨어가 에이전트에게 기본 도구를 자동으로 추가함 

TodoListMiddleware(write_todos), FilesystemMiddleware(ls, read_file, write_file, edit_file), SubAgentMiddleware(task) 등

**계획 기본 요소**

- 내장 `write_todos` 도구로 복잡한 작업을 분해하고 순차적으로 진행하며 진행 상황 또한 추적함(pending/in_progress/completed)
- 장기간에 걸친 멀티스텝 작업에 특히 유용하며, 기존 워크플로우처럼 별도의 planning agent를 두지 않아도 됨

**미들웨어 Hook**

- 에이전트 루프의 특정 지점에 코드로 강제 실행 로직 주입
- `before_model`, `wrap_tool_call` 등의 훅을 통해 메시지 주입, 도구 사용 검증, 자동 후처리 등을 구현할 수 있다.

**검증 가능성: 프롬프트 기반 + 안전망**

- 에이전트가 task를 끝내기 전 어떤 도구나 액션을 취했는지 훅을 통해 점검할 수 있음
    - 예시: 전세 조항 위험도 분석 에이전트가 분석 결과를 오케스트레이터에게 보내기 전, 미들웨어의 `after_agent` 훅에서 법령 검증용 RAG 도구 사용 여부를 확인하고, 미사용 시 재실행을 트리거할 수 있음
- 모델이 알아서 판단하는 영역(에이전틱)과, 코드로 반드시 실행되도록 보장하는 영역(미들웨어)을 분리하여 신뢰성과 유연성의 균형을 확보

**대화 흐름 안정성**

- `PatchToolCallsMiddleware`가 대응하는 ToolMessage가 없는 dangling 도구 호출을 감지하고, 자동으로 취소 메시지를 삽입하여 대화 흐름이 깨지지 않도록 한다.