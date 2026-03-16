DeepAgent-Base 컨텍스트 엔지니어링 적용 계획
Context
DeepAgent-Base는 deepagents 패키지 기반의 orchestrator + sub-agent 워크플로우 시스템이다. 현재 프롬프트 분리와 MCP 우선 사용 규칙은 잘 갖춰져 있지만, 구조화된 상태 관리, 출력 계약, 검증 루프가 부재하여 에이전트 응답 품질의 일관성이 보장되지 않는다.

리뷰어, Claude, 사용자 3자가 합의한 개선 방향을 단계적으로 적용한다.

변경 대상 파일
파일	변경 내용
backend/agent.py	프롬프트 계약 추가 (Research/Writer/Orchestrator) + 도구 초기화 일관화
backend/AGENTS.md	Done Gate 워크플로우 패턴 추가
구현 단계
Step 1: Research Agent Output Contract
파일: backend/agent.py — RESEARCH_AGENT_PROMPT (line 73~102)

프롬프트 끝에 Strict Output Contract 섹션 추가:


## Strict Output Contract
Your response MUST follow this exact structure:

### Key Facts
- fact_label: fact_value (with source if available)

### Sources
- source_name: URL or reference

### Uncertainties
- Any conflicting information or unverified claims

Do not include extra narrative outside this structure.
If no relevant results found, state "No results found" under Key Facts.
목적: 리서치 결과가 항상 정규화된 형태로 나와서 orchestrator가 writer에 전달할 때 일관성 보장.

Step 2: Report Writer Input Contract
파일: backend/agent.py — REPORT_WRITER_PROMPT (line 104~128)

프롬프트 끝에 Input Contract 섹션 추가:


## Input Contract
- Use ONLY the provided Key Facts and Sources to write the report
- If evidence is insufficient for a section, explicitly state limitations
- Do not fabricate data or sources not provided in the input
- Cross-reference Key Facts with Sources for accuracy
목적: Writer가 리서치 결과 외의 정보를 생성하지 않도록 제한.

Step 3: Orchestrator Done Gate
파일: backend/agent.py — ORCHESTRATOR_PROMPT (line 19~71)

Quality Standards 섹션 뒤에 Done Gate 추가:


## Done Gate (최종 응답 전 필수 점검)
최종 응답을 사용자에게 전달하기 전에 반드시 다음을 확인하세요:
1. 사용자 요청의 모든 요구사항이 충족되었는가?
2. 리서치 결과에 핵심 정보가 충분한가?
3. 누락된 측면이 있다면 추가 조사를 위임하세요.

요구사항이 미충족된 상태로 최종 응답하지 마세요.
부족하면 research-agent에게 추가 조사를 위임한 후 결과를 통합하세요.
목적: orchestrator가 불완전한 응답을 반환하지 않도록 자체 검증 루프 유도. deepagents의 recursion_limit: 1000 설정으로 재위임이 가능한 구조.

Step 4: 도구 초기화 일관화
파일: backend/agent.py

현재 문제 (line 157 vs 210):


# line 157: 초기 정의에서 DuckDuckGo만 하드코딩
research_agent_spec = {
    "tools": [search_tool],  # ← stale
}

# line 210: create_orchestrator()에서 재할당
research_agent_spec["tools"] = _build_research_tools()
변경: 초기 정의에서도 _build_research_tools()를 사용하고, create_orchestrator()의 재할당에 주석 추가:


research_agent_spec = {
    ...
    "tools": _build_research_tools(),  # DuckDuckGo + MCP tools (if loaded)
    ...
}

# create_orchestrator() 내부:
# Startup sync: rebuild tools to include any MCP tools loaded after module init
research_agent_spec["tools"] = _build_research_tools()
Step 5: AGENTS.md 워크플로우 패턴 보강
파일: backend/AGENTS.md

Workflow Patterns 섹션에 검증 패턴 추가:


### Verified Research Request
User asks for information -> Delegate to research-agent ->
Check: Are Key Facts sufficient? -> If not, delegate follow-up ->
Synthesize and respond with coverage confirmation
범위 외 (향후 구현 — docs/customization_roadmap.md 참조)
프롬프트 외부화, 서브에이전트 레지스트리, ExecutionState 구조화 등 개발자 커스터마이제이션 포인트에 대한 상세 로드맵은 별도 문서에 정리됨:

docs/customization_roadmap.md — Phase 2~6 구현 계획 포함:

Phase 2: 프롬프트 파일 외부화 (backend/prompts/*.md)
Phase 3: 서브에이전트 선언적 레지스트리 (agents_config.json)
Phase 4: ExecutionState + context_schema 활용
Phase 5: 출력 계약/Done Gate 구조화 설정 (backend/contracts/)
Phase 6: 환경변수 누락 보완
검증 방법
구문 검증: 서버 시작 확인 (python -m uvicorn backend.main:app)
기능 검증: 실제 채팅 요청 전송하여 research-agent가 Key Facts/Sources/Uncertainties 형태로 응답하는지 확인
Done Gate 검증: 복합 질문 전송 시 orchestrator가 재위임하는지 로그 확인
회귀 검증: 단순 인사 등 기존 direct response 패턴이 깨지지 않는지 확인