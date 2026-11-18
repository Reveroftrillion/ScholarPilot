# 실제 교과서 기반 학습 평가

`learning-cases.json`은 Bishop과 Machine Learning Systems의 실제 PDF에서 확인한 24개 질문, 근거 PDF 페이지, 핵심 개념, 설명 요소, 수식·선수 지식 여부와 확인 문자열을 기록한다. 영어와 한국어 및 간접적인 질문을 포함한다. `learning-retrieval-results.json`에 질문별 실제 검색 출처를 기록한다.

이전 파일의 한국어가 물음표로 손상돼 있었음을 이번 점검에서 발견해 UTF-8로 복구했다. 손상된 질문으로 계산한 이전 12/24 수치는 사용하지 않는다. 복구 후 근거 확인 24/24, 지정 페이지 상위 8개 적중 13/24, 반환 원문 일치 136/136, 범위 일치를 확인했다. 지정된 하나의 페이지에 대한 엄격한 적중 기준이며 다른 페이지도 타당한 근거일 수 있다. 실제 AI 설명 점수가 아니다.

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_learning.py
.\.venv\Scripts\python.exe scripts/check_learning_math.py
```

## 사람 평가 기준

각 항목을 0(오류·누락), 1(부분 충족), 2(정확·충분)로 평가하고 적용하지 않는 항목은 null로 둔다. 평가자가 원본 PDF와 답변을 대조하고 근거와 오류를 메모한다. 적용 항목 수와 점수를 함께 보고하며 null은 평균에서 제외한다.

1. grounding: 원문 의미와 범위를 반영한다.
2. symbols: 수식 기호, 차원과 역할을 정확하게 설명한다.
3. derivation: 유도 단계와 등식에 오류가 없다.
4. assumptions: 가정과 적용 조건을 명시한다.
5. example: 예제를 정확하게 계산하고 생성 예제임을 표시한다.
6. prerequisites: 필요한 선수 지식을 정확히 연결한다.
7. citations: 주장과 책·PDF 페이지가 일치한다.
8. korean_clarity: 한국어 설명이 단계적이고 이해하기 쉽다.
9. uncertainty: 근거 부족과 PDF 추출 오류를 명시한다.

독립 계산 스크립트는 베이즈 사후확률, 1차원 경사 갱신, softmax 정규화 예제를 확인한다. 교과서의 원래 숫자라고 주장하지 않는다. 실제 응답이 사용하는 숫자와 유도는 추가로 직접 검토해야 한다.

## 실제 응답 기록

범용 기록 예시는 `learning-record-example.json`, 구조 검사기는 `scripts/validate_learning_record.py`다. 모델, 문맥, 검색 출처, 도구, 응답, 시간, 토큰, 가격 기준과 비용 추정, 평가자와 점수를 기록한다. 알 수 없는 사용량·가격과 미평가 점수는 null로 둔다.

Bayes 시나리오는 `scripts/bayes_evaluation.py`가 이 양식에 맞춰 호출과 응답을 자동 기록한다. 자세한 승인 조건과 실행법은 [BAYES_LIVE_PREFLIGHT.md](BAYES_LIVE_PREFLIGHT.md)를 따른다. 다른 시나리오는 수동 기록이 필요하다. 실제 API 미호출: 실제 AI 품질 점수와 사용자 학습 효과는 미검증이다.

## 시험 데이터 관리

`scripts/inspect_test_storage.py`는 benchmarks, evaluation-runs, browser-qa-runs, bayes-evaluation-runs의 목적과 용량을 조회하는 dry-run이다. 삭제하지 않는다. 새 Bayes 평가는 실행별 격리 폴더를 생성한다. 브라우저 재검증은 기존의 표시 파일이 있는 QA 폴더를 `--resume`으로 재사용해 PDF 복사를 줄였다. 사용자 데이터 및 시험 데이터를 이번 작업에서 삭제하지 않았다.
