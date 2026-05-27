"""AI 에이전트 패키지.

v0.1 — Sonnet 단일 모델 (모든 에이전트 claude-sonnet-4-6)
v0.2 — Critic → Opus 4.7 교체 (검증 품질·할루시네이션 감지 강화)
v0.3 — ProfileAnalyzer → Haiku 4.5 분리 (3-tier 비용 최적화)

3-tier 모델 라우팅 (v0.3 최종):
  Tier 1 — claude-haiku-4-5  : profile_analyzer (분류·태깅)
  Tier 2 — claude-sonnet-4-6 : curriculum_designer, resource_curator (생성)
  Tier 3 — claude-opus-4-7   : critic (검증·교차확인)

설계 의도:
  단순 분류 작업(기술 스택 태깅)은 Haiku로 처리해 응답 속도↑, 비용↓
  복잡한 생성 작업은 Sonnet + Prompt Caching으로 품질/비용 균형
  최종 검증은 Opus로 할루시네이션·기술 오류를 정밀 감지
"""
