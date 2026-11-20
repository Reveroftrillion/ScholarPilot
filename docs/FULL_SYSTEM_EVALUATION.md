# ScholarPilot 전체 시스템 실사용 평가

전체 교과서를 완독 검증했다는 뜻이 아니다. 두 책의 여러 장에서 실제 페이지를 표본 평가했다. 유효한 JSON, 출처 ID, needs_review 상태는 의미 정확성의 통과 판정이 아니다.

## 환경과 재현

- Windows / Ryzen 5 7500F / RAM 16GB / RTX 5070 12227 MiB, 드라이버 621.01
- Ollama 0.40.16 / qwen3:8b / 문맥 4096 / 로컬 FastAPI + React / 외부 유료 호출 0
- 기준 커밋: f4bbda96b1e6300d92d327123739e06954f522bb
- 평가 DB는 scripts/local_validation_server.py로 만든 책·검색 인덱스 복사본. 사용자 세션·답안은 복사하지 않았다.
- scripts/full_system_evaluation.py → scripts/full_system_browser.cjs → 실패 사례 재실행. 브라우저는 실제 PDF text layer 선택과 번역 버튼, 출처 클릭, 새로고침을 사용한다.
- 원문·요청·응답·출처·시간·메모리는 ignored data/local-evaluation-runs/ 아래에만 저장한다. 이 보고서에는 원문 대량 발췌가 없다.

## 실행 규모

- 고유 사례 147개, 기록된 초기/추가/브라우저 시도 152개, 별도 API 재실행 34개
- 실제 생성 토큰이 확인된 Ollama 호출 189회 / provider 시도 기록 189회. Mock·캐시 결과 없음.
- 서로 다른 책·PDF 페이지 48개; 고유 브라우저 시나리오 20개
- API 기본 평가와 후반부 보완은 기준 코드로 실행했다. 브라우저는 초기 실패 후 일부 수정본에서 이어 실행했으며 원본 시도도 남겼다. 아래 유형별 상태는 API 기본 결과와 브라우저의 마지막 시도이며 전체 의미 정확도나 동일 버전 성공률이 아니다.
- 시간(전체 사례): 중앙값 5.08초, p95 12.33초, 최대 15.69초
- 시간은 서버/브라우저 처리 시간을 포함한다. 서로 다른 작업의 시간을 모델 성능 비교로 해석하지 않는다.

| 유형 | 실행 | 상태 분포 |
|---|---:|---|
| explain | 20 | {'needs_review': 20} |
| page | 15 | {'needs_review': 15} |
| follow | 15 | {'needs_review': 15} |
| math | 15 | {'needs_review': 12, 'error': 3} |
| search | 10 | {'needs_review': 10} |
| visual | 10 | {'completed': 4, 'needs_review': 6} |
| quiz | 10 | {'error': 7, 'awaiting_answer': 3} |
| error | 6 | {'completed': 4, 'error': 1, 'expected_connection_error': 1} |
| coverage | 8 | {'needs_review': 8} |
| formula | 8 | {'needs_review': 8} |
| translate | 20 | {'needs_review': 20} |
| edge | 10 | {'needs_review': 6, 'awaiting_answer': 2, 'completed': 2} |

## 책·페이지 분포

| 책 | PDF 페이지 | 인쇄 페이지 | 목차상 절 |
|---|---:|---|---|
| Bishop | 28 | 8 | 1.2.3 Error function |
| Bishop | 32 | 12 | 1.2.5 Regularization |
| Bishop | 46 | 26 | 2.1.2 The sum and product rules |
| Bishop | 48 | 28 | 2.1.3 Bayes’ theorem |
| Bishop | 54 | 34 | 2.2.2 Expectations and covariances |
| Bishop | 85 | 66 | 3.1.1 Bernoulli distribution |
| Bishop | 95 | 76 | 3.2.4 Conditional distribution |
| Bishop | 134 | 115 | 4.1.3 Maximum likelihood |
| Bishop | 137 | 118 | 4.1.6 Regularized least squares |
| Bishop | 159 | 140 | 5.2.2 Expected loss |
| Bishop | 194 | 176 | 6.1.3 Data manifolds |
| Bishop | 219 | 201 | 6.5.3 Gradient optimization |
| Bishop | 231 | 214 | 7.2.3 Stochastic gradient descent |
| Bishop | 252 | 235 | 8.1.2 General feed-forward networks |
| Bishop | 275 | 258 | 9.1.3 Symmetry and invariance |
| Bishop | 306 | 290 | 10.2.1 Feature detectors |
| Bishop | 350 | 334 | 11.1.6 Parameters and observations |
| Bishop | 377 | 361 | 12.1.2 Attention coefficients |
| Bishop | 382 | 366 | 12.1.6 Multi-head attention |
| Bishop | 451 | 436 | 14.1.4 Adaptive rejection sampling |
| Bishop | 480 | 465 | 15.1.1 Image segmentation |
| Bishop | 516 | 502 | 16.1.4 Data whitening |
| Bishop | 550 | 537 | 17.1.2 GAN training in practice |
| Bishop | 595 | 585 | 20.2. Reverse Decoder |
| ML Systems | 84 | 12 | Defining ML Systems |
| ML Systems | 104 | 32 | Characteristics |
| ML Systems | 138 | 66 | System Scaling |
| ML Systems | 164 | 92 | Implementation Aspects |
| ML Systems | 197 | 125 | Algorithmic Structure |
| ML Systems | 232 | 160 | Deployment Requirements and Impact |
| ML Systems | 251 | 179 | Existing Datasets |
| ML Systems | 267 | 195 | Continuing the KWS Example |
| ML Systems | 315 | 243 | Memory Consequences |
| ML Systems | 375 | 303 | Advanced Optimization Algorithms |
| ML Systems | 411 | 339 | Data Parallelism |
| ML Systems | 442 | 370 | Empirical Scaling Laws |
| ML Systems | 498 | 426 | Unstructured Pruning |
| ML Systems | 535 | 463 | Post-Training Quantization |
| ML Systems | 544 | 472 | Quantization-Aware Training |
| ML Systems | 554 | 482 | Memory Optimization |
| ML Systems | 614 | 542 | Memory-Intensive ML Workloads |
| ML Systems | 647 | 575 | Tiling for Memory Efficiency |
| ML Systems | 703 | 631 | Benchmark Harness |
| ML Systems | 730 | 658 | Inference Benchmark Pitfalls |
| ML Systems | 762 | 690 | Inference Serving |
| ML Systems | 1010 | 938 | Carbon-Aware Scheduling |
| ML Systems | 1288 | 1216 | Resources |
| ML Systems | 1514 | 1442 | EfficientDet |

## 원문 직접 대조 검토

모델 자기평가를 사용하지 않았다. 각 행의 판단은 평가자가 원문과 실제 응답을 대조한 제한적 검토이며, 일반적인 증명을 인증하지 않는다. 번역 검토 행에는 문장 순서·절의 논리·기호 보존 여부를 기록한다.

| 사례 | 판정 | 원문·논리·계산 대조 결과 |
|---|---|---|
| explain-01 | 대체로 일치 | 규칙과 관측 노이즈 구분. 온도 예시는 원문 사례와 구분 필요. |
| explain-02 | 부분 일치 | 원문은 시스템 정의의 필요성을 제기하지만 응답은 전통 소프트웨어 비교를 추가함. |
| explain-03 | 부분 일치 | 캡션의 N=15/100과 과적합 감소는 일치. 모든 데이터 증가의 효과로 일반화하지 않아야 함. |
| explain-04 | 오류/미지원 주장 | 클라우드 자원 풀링은 일치. 서버 증가가 모델 성능 개선을 보장한다는 예시는 근거 없음. |
| explain-05 | 대체로 일치 | 비암 3/100 양성, 암 90/100 양성을 보존. 전체 정확도 수치는 계산하지 않음. |
| explain-06 | 부분 일치 | 행렬 병렬 처리 핵심은 일치. 영화를 동시에 본다는 비유는 직관에 부적절. |
| explain-07 | 부분 일치 | 표기 간소화는 일치. p(xi)를 특정 값에서 평가한 값 대신 분포라고 표현함. |
| explain-08 | 불완전 | 선택문은 첫째 이유까지만 있음. 두 가지라고 시작하고 둘째 이유를 제공하지 않음. |
| explain-09 | 대체로 일치 | 델타 적분 1과 경험분포 가중치 1/3, 세 관측 예시의 정규화 일치. |
| explain-10 | 대체로 일치 | bank/river와 bank/loan의 문맥 구분 일치. |
| explain-11 | 오류/과잉 일반화 | 원문 i.i.d.는 이 장의 가정. 구조화된 데이터에 모수분포를 쓸 수 없다는 식의 대비는 부정확. |
| explain-12 | 대체로 일치 | 개발과 데이터·인프라·배포 간 반복적 피드백 보존. |
| explain-13 | 대체로 일치 | 캡션의 일반/대각/등방 공분산별 등고선 관계 일치. 캡션 기반임을 더 명확히 표시해야 함. |
| explain-14 | 오류/근거 부족 | 벤치마크 표준화는 일치. 이미지 수와 정확도 90% 수치는 선택 원문에 없으며 보장 불가. |
| explain-15 | 부분 일치/추출 한계 | 독립 관측과 w,분산의 가능도는 일치. 굵은 글꼴 t 구분이 PDF 텍스트에서 유실되어 같은 기호로 반복. |
| explain-16 | 대체로 일치 | 전처리 속도 이점, 저장량·staleness, 혼합 방식 보존. |
| explain-17 | 수식 문맥 누락 | 선택 문단의 제곱합 설명만 보면 4+9=13이지만, 같은 페이지 식 4.24의 EW에는 1/2가 있어 실제 값은 6.5. 선택 문단 바로 뒤 수식의 근거 누락을 확인. |
| explain-18 | 대체로 일치 | backward 연산 재배치와 하드웨어 전용 연산의 목적 보존. |
| explain-19 | 오류 | p(Ck|x)를 사전 확률로 잘못 명명. 원문은 사후 확률. 0.7 대 0.3의 선택 자체는 옳음. |
| explain-20 | 과잉 일반화 | 병렬 미니배치의 효율·메모리 관계는 맞지만 배치가 클수록 항상 빠르다는 단정은 원문보다 강함. |
| translate-01 | 대체로 충실 | 첫 문장 가우시안 노이즈 추가와 tn을 보존. 다음 두 문장의 규칙성/관측 오염, 방사성 붕괴와 미관측 변동성의 대조를 유지. 여백 Section 2.3은 생략. |
| translate-02 | 충실 | 양성 뒤 실제 암 확률 질문, 사례 분석 가능성, 논의 유보, 합·곱 규칙 도출, 두 질문에 적용하는 문장 순서를 보존. 요약으로 대체하지 않음. |
| translate-03 | 대체로 충실 | 라플라스 위치 이동 문장과 1/(2gamma) exp(-abs(x-mu)/gamma), 그림2.7 참조, 디랙 델타 정의까지 모두 전달. 원문 수식의 분모 두 곳을 보존. |
| translate-04 | 부분 일치 | 자유도 감소/역행렬 속도 이점과 상관 포착 제한의 대조, 단봉/다봉 한계를 보존. 선택 끝이 단어 중간에서 잘려 마지막 절의 완전 충실도는 확정 불가. |
| translate-05 | 수정 후 기능 복구 | 실제 선택문을 처음에는 거부해 생성 0회. 전체 정렬 범위 검사 수정 후 SGD 도입 문장, E 합, 업데이트 식4.21, tau 반복/eta 학습률을 순서대로 번역. 여백 Chapter7은 생략. 공백 trim은 내용 누락과 구분. |
| translate-06 | 부분 일치/용어 | 고차원 가우시안, 좌표 변환, 방향 변수 적분 제거, 반지름 밀도, 얇은 껍질 확률질량을 보존. integrate out을 통합으로 옮겨 수학 용어는 부정확. p(r)delta r 기호는 보존. |
| translate-07 | 대체로 충실 | 시작점 반복/독립 검증 세트 비교, 절 제목, 역전파의 효율적 기울기와 학습 가속을 보존. 문장 시작이 앞 페이지/앞줄에서 이어지는 조각임에 유의. |
| translate-08 | 오류 | 증강 항목 a~h와 접선전파·정규화 항 문장은 유지. 원문의 additive noise를 Gaussian noise로 좁혀 원문에 없는 가정을 추가. 완전 충실 번역 실패. |
| translate-09 | 수정 전 오류 / 수정 후 개선 | 이진 분류기와 t1..tN,w는 보존했으나 joint distribution의 결합 의미가 약화됨. 선택문에 없는 제2장6.2절을 추가. 청크 뒷부분을 번역 근거로 넘긴 공통 원인을 수정 대상으로 분류. 수정 후 실제 재생성에서는 결합 분포를 명시하고 선택 밖 절 참조를 추가하지 않음. |
| translate-10 | 수정 전 오류 / 수정 후 개선 | 표준 신경망의 모든 입력 무시와 softmax 기울기 축소·재스케일 순서는 보존. 선택은 note that에서 끝나지만 독립/평균0/분산1 및 Dk, 연습문제12.4를 추가해 선택 범위를 벗어남. 선택문만 근거로 제한한 뒤 실제 재생성에서는 선택 마지막 note that에 맞춰 멈추고 분산 가정을 추가하지 않음. |
| translate-13 | 의미 오류 | 그래프 관계/동적 처리와 bank의 두 문맥을 옮겼지만 bank by river를 강변의 은행으로 번역. 강둑이라는 핵심 다의어 해석에 실패. 잘린 RNN 절도 임의로 완성. |
| translate-18 | 수식 의미 누락 | QAT 전방향 양자화/역전파 full precision과 STE는 유지. rounding derivative of one의 1이라는 핵심 조건을 생략. 잘린 인용문 뒤 참고문헌을 선택 밖에서 추가. |
| translate-20 | 대체로 충실/원문 한계 | 배포 전환, 모델 크기, 지연 ms/inference, 에너지/효율 지표, 정확도와 효율의 균형을 문장별로 보존. watts와 energy의 단위 혼용은 원문에도 있어 모델 오류와 구분. |

## 기능별 결과와 한계

- 출처 ID·책·페이지·저장 청크 일치: 검사한 371개 인용 출현에서 불일치 0개. 이것은 내용 관련성이나 진술의 참을 뜻하지 않는다.
- 브라우저 고유 20개에서 선택 내용(trim 제외) 전달·원문 보존 20/20, 출처 이동 20/20, 페이지·대화 복원 20/20. 20개 모두 실제 번역을 생성했다. 의미 정확도 통과와 구분한다.
- 15개 연속 대화 요청에서 학습 대상은 유지됐으나 수치 예제의 정확성까지 보장되지 않는다. 다른 페이지/책의 역사 로딩과 새 대화가 겹치는 문제도 발견했다.
- 전체/현재 책 검색을 각각 수행했다. 없는 주제에서 현재 첫 문단을 억지 근거로 사용한 2개 사례를 수정 후 0회 생성·출처 없음으로 차단했다. AND 키워드 검색은 여전히 표현 변화에 취약하며 chapter 번호만으로 특정 범위를 확정하는 기능은 검증되지 않았다.
- 그림뿐 아니라 표·축 요청도 텍스트 모델이 직접 이미지를 본 것처럼 답하지 않도록 처리한다. 실제 Figure/Table 캡션만 추출한다. 이미지, 벡터 도형, 표 셀 구조의 직접 해석은 미지원이다.
- 실제 생성된 미검증 퀴즈의 정답 후보 제출은 불확실로 남겼으며 이해도를 인증하지 않았다. 중복 답안은 새로 저장되지 않았다. Python 계산 문제의 정·오답은 독립 채점했다.

## 공통 오류와 수정 전후

| 공통 원인 | 수정 전 | 수정 후 실제 확인 |
|---|---|---|
| 상대 페이지를 검색어로 처리 | 다음 페이지 3건은 현재 페이지, 비교 3건은 한 페이지만 인용 | 443/276/615로 이동, 230·231 / 543·544 / 376·377 두 페이지를 제공하고 각각 인용 |
| 수식 글리프 차이에서 단일 연속 일치 요구 | 실제 PDF 선택문인데 거부, 생성 0회 | 순서 있는 전체 일치 범위 검사로 동일 선택문 번역 성공. 무관한 선택은 계속 거부 |
| 번역에 청크 뒷문장도 포함 | 선택 밖 장/절·독립성 가정과 분산 설명 추가 | 선택문만 번역 근거로 제공. 두 실패 문단을 실제 재생성해 추가 문장 제거 확인 |
| 검색 실패 시 현재 첫 문단 사용 | 유니콘 질문에 신경망/랩 페이지를 인용 | 근거 없음 안내, 출처 없음, 모델 호출 0회 |
| 표·그래프 의도 누락 | 시각 요청 6건이 텍스트 생성으로 진행 | 같은 6건 모두 직접 분석 미지원·캡션 안내, 생성 0회 |
| 검산기 미지원 구문을 수학 오류로 표시 | 지수 표기 등 지원 못 하는 등식도 hard fail | 미검증으로 분리. 1/0 및 계산값 불일치의 오류 경고는 유지 |
| 객관식 choices가 선택 필드 | 4개 객관식에서 선택지 누락 | JSON 스키마에 필수 선택지/최소 2개 명시; 실제 재생성 4개 모두 저장 가능 |
| 수치 정답 문자열 제약 부족 | 숫자 대신 용어·수식, 오류 3건 | 숫자 패턴과 안전한 유한수 검사. 수치 3건 중 2건 생성 성공, 1건은 계속 거부됨 |
| 선택 문단 직후 수식 근거 누락 | 정규화 문단 다음 식의 계수1/2 누락 | 인접 청크 제공을 보완했지만 해당 모델 예시는 여전히 13을 제시함. EW=6.5인 원문과 불일치하므로 미해결 |

기본 퀴즈 10개 중 오류 7개. 실패한 7개를 수정 후 재생성해 6개는 문제 저장, 1개는 수치 정답을 생성하지 못해 저장 거부. 저장 성공이 문제·정답의 의미 정확성 인증은 아니다.

재현 도구에서도 두 문제를 수정했다: 기록 로딩 전에 새 대화를 눌러 복원과 경합하는 순서, 다른 동시 답안 제출의 결과를 history 마지막 행으로 잘못 연결하는 방식이다. 첫 실패 시도는 보존하고, 현재는 동일 page/selection/task 요청과 응답을 연결한다. 기본 평가와 수정 후 검증에 사용한 버전을 혼동하지 않는다.

## 수식 독립 검산

실제 페이지의 수식 존재를 원문에서 확인한 별도 formula 8건과 기본 math 15건을 실행했다. 기본 math에는 수식이 없는 시스템 문단의 요청도 포함되어 있으며, 이를 수식 정확성 통과로 세지 않았다. 추가로 경사하강, 역전파, CNN, 분류기 결합분포, attention, PTQ/QAT의 실제 등식 페이지를 보완했다.

Bishop 식4.24의 EW=(1/2)sum(w_j^2)에 예시 가중치 (2,3)를 대입하면 SymPy 결과는 13/2=6.5이다. 실제 프로그램의 계산 문제에서 6.5 정답/13 오답을 독립 채점했다. 이 결과는 계산 연습이며 일반 개념 이해 인증이 아니다. 미검증 의미 문제 3개에 대해 정답 후보와 중복 오답 제출을 실행했고 확정 채점하지 않았다.

반면 생성된 attention 식에서 V 누락, Bernoulli를 이항 분포로 부르는 혼동, 1/2·lambda·분자/분모 누락, 잘못된 LaTeX 등이 관찰됐다. 기존 제한적 산술 검사가 이를 모두 검출하지 못한다. 일반적인 유도·증명 및 선택 원문 의미의 정확성은 미검증이다.

## 최종 남은 문제

1. 설명과 수학 예제의 의미 정확성: 원문에 없는 가정/성능 수치, 사전·사후확률 용어 혼동, 정규화 계수 누락이 남는다. 모델 변경이나 새로운 실험으로 덮지 않았다.
2. 번역: bank/river의 bank를 은행으로 번역, additive를 Gaussian으로 좁힘, STE의 도함수1 생략, 비표준 기술 용어가 관찰됐다. 범위 전달 수정은 이런 추론 오류의 완전 해결이 아니다.
3. 수치 퀴즈 1건은 최종 후보가 숫자가 아닌 수식이라 거부했다. 잘못된 문제는 저장하지 않는다. 모델의 의미 정답은 이해도에 확정 반영하지 않는다.
4. 그림·표 이미지 해석은 미지원. 직접 분석으로 표시하지 않는다. OCR, 글꼴 굵기/첨자·다단 수식 추출, 잘린 문장에는 한계가 있다.
5. 최초 계측은 거부된 JSON의 최종 원문을 보존하지 못하고 오류·메트릭만 기록했다. 정상 설명은 실제 API 응답과 연결해 보존했다. 재검증부터는 내부 thinking을 제외한 최종 wire 응답도 저장하도록 개선했다. 초기 거부 응답을 복원했다고 주장하지 않는다.
6. 메모리 압박: 평가 중 최소 가용 RAM 0.10 GiB, 후속 조회 약0.99 GiB; llama-server 작업 집합 약7.86 GiB. 16GB 시스템에서 큰 PDF/모델 병행에 주의가 필요하다. API 모델 적재 VRAM 표본 최대 4.86 GiB, nvidia-smi 전체 사용 표본6432 MiB. 서로 다른 메모리 지표이며 최대 순간 사용량을 보증하지 않는다.
7. 실제 생성 호출의 중앙값 4.23초, p95 11.25초. 초기 API 사례(서버 안내 포함) 중앙값 4.87초, p95 13.95초. 브라우저 마지막 시도 중앙값 10.47초. 전체 의미 정확도를 하나의 성공률로 환산하지 않았다.

사용자 원본 DB의 books/runs/sessions/attempts/mastery/highlights 내용 해시가 평가 전후 동일했다. PDF·Ollama 모델·.env는 변경하지 않았으며 원문 로그는 Git에서 제외한다.

## 회귀 테스트

백엔드 183개 통과, 프론트엔드 14개 통과, 프론트엔드 빌드 성공. 최종 오류 안내/표 출처 보완 뒤 집중 검사를 추가 확인했다. 기존 Starlette 폐기 예정 경고와 Vite 번들 크기 경고는 남아 있다.
