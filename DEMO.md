# ScholarPilot Bayes 학습 데모

1. `scripts/start.ps1` 실행 후 http://127.0.0.1:8000 에 접속하고 Bishop을 연다.
2. PDF 48페이지(인쇄 28페이지)의 Bayes 정리를 선택하고 한국어 설명을 요청한다. 기호, 곱의 법칙을 이용한 유도, 적용 조건과 생성 계산 예제를 확인한다.
3. 이해하지 못했다고 입력하고 조건부확률 등 선수 지식 검색과 확인 문제를 요청한다.
4. 실행 로그의 `search_textbook`, `find_prerequisites`, `explain_concept`, `generate_quiz` 결과와 출처 페이지를 확인한다. 실제 모델의 도구 선택 순서는 고정돼 있지 않다.
5. 문제를 낸 뒤 대기가 유지되는지 확인하고 새로고침해 문제를 복원한다.
6. 오답을 제출하고 `evaluate_answer`, `update_mastery`, `recommend_next_topic` 및 복습 필요 상태를 확인한다.
7. 선수 개념을 보충하고 새 진단을 요청한다. 대시보드를 새로고침해 저장된 기록을 확인한다.

기본 Mock은 원문을 이용한 로컬 동작이다. 실제 생성형 한국어 설명과 모델의 도구 판단은 OpenAI 연결과 사용자 승인이 필요하다. 현재 실제 모델 품질은 검증하지 않았다.

승인 전에는 `python scripts/bayes_evaluation.py --mode offline`으로 실제 Bishop PDF를 사용하는 전체 상태 흐름과 자동 기록을 검증한다. 이는 정해진 오프라인 모델 대역이다. 브라우저 검증용 `browser_fixture.py --mode bayes`도 외부 호출을 하지 않는다.

실제 유료 평가의 모델, 요청 수와 비용 제한, 키 설정 및 실행 명령은 [BAYES_LIVE_PREFLIGHT.md](docs/BAYES_LIVE_PREFLIGHT.md)에 있다. 평가 실행기는 사용자 기록을 포함하지 않는 격리 DB를 사용한다. 평소 앱에서 직접 수행한 답안과 기록은 사용자 학습 기록에 저장된다.

[학습 평가 기준](docs/LEARNING_EVALUATION.md), [Agent 비교](docs/AGENT_VS_RAG.md), [평가 결과](docs/EVALUATION_REPORT.md).
