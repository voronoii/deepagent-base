## 이전 답변

1차 검토 완료. 핵심은 **프롬프트는 잘 갖췄지만, deepagents 컨텍스트 엔지니어링의 “구조화된 상태/요약/검증 루프”가 약함**입니다.

**현재 강점**
- 역할 분리: orchestrator / research / writer 프롬프트 분리 (`backend/agent.py:19`, `73`, `104`)
- MCP 우선 사용 규칙 명시 (`backend/agent.py:81-87`)
- 컨텍스트 윈도우 인지 설정(`model.profile`)로 SummarizationMiddleware 트리거 기반 마련 (`backend/config.py:35-56`)
- AGENTS.md 기반 메모리 주입 설계 문서화 (`docs/CUSTOMIZATION_GUIDE.md:166-170`)

**주요 갭**
- 상태 스키마가 API 레벨만 있고 에이전트 실행 상태(goal/constraints/done_criteria 등) 구조가 없음 (`backend/schemas.py:7-34`)
- tool 결과 정규화 계층 부재(원문 결과→다음 스텝 직접 전달 가능성 큼)
- critic/replanner(자체 검증) 루프 없음
- 종료 게이트(요구사항 충족 체크리스트) 없음
- `research_agent_spec["tools"]` 초기값과 동적 재구성 혼재로 의도 불명확 (`backend/agent.py:157`, `210`)

**효과적으로 넣는 우선순위(추천)**
1) **실행 상태 구조화**: LangGraph state에 `goal/constraints/context_budget/findings/open_questions/done_criteria` 추가  
2) **정규화 노드 추가**: 리서치 결과를 `key_facts/sources/uncertainties`로 압축 후 writer에만 전달  
3) **검증 노드 추가**: 최종 응답 전 “요청 문장별 충족 여부” 검사 실패 시 재계획  
4) **컨텍스트 예산 룰**: “최근 N결정 + 관련 근거만” 주입(전체 히스토리 금지)  
5) **완료 게이트**: done_criteria 미충족 시 종료 금지

원하시면 다음으로 `backend/agent.py` 기준 **구체 패치안(노드 구성/상태 타입/프롬프트 템플릿)**까지 바로 작성해드리겠습니다.

---

## 지금 답변

좋습니다. 바로 반영하려면 아래 3개 파일 패치가 가장 안전합니다.

### 1) `backend/schemas.py`에 실행 상태 스키마 추가
```python
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class ContextBudget(BaseModel):
    max_input_tokens: int = 32768
    reserve_output_tokens: int = 4096
    recent_turns: int = 6

class Finding(BaseModel):
    fact: str
    source: str = ""
    confidence: str = "medium"  # low|medium|high

class ExecutionState(BaseModel):
    goal: str
    constraints: List[str] = []
    done_criteria: List[str] = []
    open_questions: List[str] = []
    key_facts: List[Finding] = []
    uncertainties: List[str] = []
    context_budget: ContextBudget = Field(default_factory=ContextBudget)
```

### 2) `backend/agent.py`에 정규화 + 검증 프롬프트 추가
- `RESEARCH_AGENT_PROMPT` 끝에:
```text
## Strict Output Contract
Return ONLY:
- key_facts: bullet list of "label: value"
- sources: bullet list of URLs or source names
- uncertainties: bullet list
Do not include extra narrative.
```

- `REPORT_WRITER_PROMPT` 끝에:
```text
## Input Contract
Use only provided key_facts/sources/uncertainties.
If evidence is insufficient, explicitly state limitations.
```

- Orchestrator prompt에 완료 게이트 추가:
```text
## Done Gate (must pass before final answer)
- Check every user requirement is addressed.
- If any requirement is missing, delegate follow-up task first.
- Include a short "Coverage Check" section internally before responding.
```

### 3) `backend/agent.py` 도구/컨텍스트 일관화
- `research_agent_spec["tools"]`를 초기부터 동적 빌더로 통일:
```python
research_agent_spec = {
    ...
    "tools": _build_research_tools(),
    ...
}
```
- `create_orchestrator()`에서 재할당은 유지 가능하되 주석으로 “startup sync” 명시.

원하면 다음 답변에서 제가 실제 파일에 바로 edit 적용까지 진행하겠습니다.

---

## 방금 답변

동의합니다. Claude 리뷰가 정확하고 실무적으로 더 안전합니다.

핵심 정리:
- 제안 방향(구조화/검증 강화)은 맞음.
- 다만 **ExecutionState는 “어디에 연결할지”가 빠진 상태**라 바로 코드 추가하면 사장될 수 있음.
- 현 구조(`create_deep_agent`)에선 **프롬프트 계약(Research/Writer/Done Gate)**이 즉시 적용 가능한 최적해.
- SummarizationMiddleware가 기본 컨텍스트 예산을 이미 일부 해결한다는 지적도 맞음.

권장 실행 순서도 Claude 제안(1→4 즉시, 5 설계 후)이 맞습니다.  
원하면 지금 `backend/agent.py`에 1~4번을 바로 반영하겠습니다.

---

## Claude 의견(전문)

리뷰어의 핵심 진단 — "프롬프트는 잘 갖췄지만, 구조화된 상태/요약/검증 루프가 약하다" — 이 부분은 코드를 직접 확인해 봐도 맞습니다.

현재 프로젝트의 실제 상태를 보면:

schemas.py — API 레벨 스키마(ChatRequest, MessageData)만 있고, 에이전트 실행 상태(goal, done_criteria 등) 구조 없음
agent.py:157 — research_agent_spec["tools"]가 초기에 [search_tool]로 세팅된 뒤 agent.py:210에서 재할당되는 혼재 패턴
검증/critic 노드 없음, 종료 게이트 없음 — 이것도 확인됨
다만 제안된 패치에 대해 주의할 점이 있습니다
1) ExecutionState 스키마 추가 제안 — 방향은 맞지만 적용 방법이 불명확

리뷰어가 제안한 ExecutionState Pydantic 모델은 개념적으로는 좋지만, deepagents의 실제 아키텍처와 어떻게 연결되는지가 빠져 있습니다. deepagents는 LangGraph의 state를 messages + files 중심으로 관리합니다.

ExecutionState를 실제로 활용하려면:

create_deep_agent의 context_schema 파라미터를 사용하거나
커스텀 미들웨어를 작성해서 state에 주입하거나
프롬프트 안에 구조화된 형태로 인라인 관리
이 중 어떤 경로를 택할지에 따라 구현이 크게 달라집니다. 리뷰어는 이 부분을 명시하지 않았습니다.

2) 정규화 노드 추가 — 현실적 제약 존재


리서치 결과를 key_facts/sources/uncertainties로 압축 후 writer에만 전달
이 제안은 이상적이지만, deepagents에서 서브에이전트 간 데이터 전달은 orchestrator가 중간에서 relay하는 구조입니다 (SubAgentMiddleware → task tool). 별도의 "정규화 노드"를 LangGraph 그래프에 끼워넣으려면 create_deep_agent를 사용하지 않고 직접 그래프를 구성해야 합니다.

더 현실적인 방법: 리서치 에이전트의 Output Contract를 프롬프트로 강제하는 것이 deepagents 구조 내에서 가장 간단합니다. 이 부분은 리뷰어도 제안했고, 이게 실제로 적용 가능한 첫 번째 단계입니다.

3) 검증 노드 / 완료 게이트 — 가장 가치가 높은 부분

Orchestrator 프롬프트에 Done Gate를 추가하는 것은 즉시 적용 가능하고 효과가 큽니다. 단, "실패 시 재계획"은 deepagents의 create_deep_agent가 이미 recursion_limit: 1000으로 설정되어 있어서 (graph.py:251), orchestrator가 스스로 재위임할 수 있는 구조입니다. 별도 노드 없이 프롬프트 지시만으로도 자체 검증 루프가 가능합니다.

4) 컨텍스트 예산 룰 — deepagents가 이미 일부 커버

SummarizationMiddleware가 이미 trigger=("fraction", 0.85), keep=("fraction", 0.10)으로 설정되어 있고 (config.py:35-56 → graph.py:150-151), 대화 히스토리를 자동 요약/오프로드합니다. "최근 N결정만 주입" 같은 세밀한 제어는 추가 미들웨어가 필요하지만, 기본적인 예산 관리는 이미 작동하고 있습니다.

제가 추천하는 우선순위
순위	작업	난이도	영향도	방법
1	Research Output Contract (프롬프트)	낮음	높음	RESEARCH_AGENT_PROMPT에 Strict Output Contract 추가
2	Done Gate (프롬프트)	낮음	높음	ORCHESTRATOR_PROMPT에 Coverage Check 섹션 추가
3	Writer Input Contract (프롬프트)	낮음	중간	REPORT_WRITER_PROMPT에 Input Contract 추가
4	도구 초기화 일관화	낮음	낮음	research_agent_spec["tools"]를 _build_research_tools()로 통일
5	ExecutionState 구조화	높음	높음	context_schema 또는 커스텀 미들웨어 — 설계 먼저 필요
요약: 리뷰의 1~3번(프롬프트 레벨 변경)은 바로 적용해도 좋습니다. 4번 도구 일관화도 간단합니다. 5번 ExecutionState 스키마 구조화는 deepagents의 state 관리 구조와 맞물려야 하므로 설계를 먼저 한 뒤 진행하는 게 안전합니다.

적용을 진행할까요? 프롬프트 레벨 개선(1~3번)부터 시작하면 리스크 없이 바로 효과를 볼 수 있습니다.

---

## 제 답변(전문)

동의합니다. Claude 리뷰가 정확하고 실무적으로 더 안전합니다.

핵심 정리:
- 제안 방향(구조화/검증 강화)은 맞음.
- 다만 **ExecutionState는 “어디에 연결할지”가 빠진 상태**라 바로 코드 추가하면 사장될 수 있음.
- 현 구조(`create_deep_agent`)에선 **프롬프트 계약(Research/Writer/Done Gate)**이 즉시 적용 가능한 최적해.
- SummarizationMiddleware가 기본 컨텍스트 예산을 이미 일부 해결한다는 지적도 맞음.

권장 실행 순서도 Claude 제안(1→4 즉시, 5 설계 후)이 맞습니다.
원하면 지금 `backend/agent.py`에 1~4번을 바로 반영하겠습니다.
