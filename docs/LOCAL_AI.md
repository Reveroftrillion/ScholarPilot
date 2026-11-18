# 로컬 AI 설치·검증 안내

2026-11-18 기준입니다. 실제 AI 생성은 이 PC의 Ollama에서 수행합니다. `Mock`, 오프라인 모델 대역, 실제 로컬 모델은 구분하여 기록합니다. 외부 유료 AI 요청은 금지하며 OpenAI 크레딧은 필요하지 않습니다.

## 설치와 모델 선택

현재 CPU는 i5-1240P, RAM은 약 8 GB, GPU는 Intel Iris Xe 내장형입니다. Qwen3 4B(가중치 약 2.5 GB)와 8B(약 5.2 GB)를 우선 검토했으나 초기 가용 RAM이 약 0.87 GiB로 작았습니다. 런타임·KV 캐시·브라우저까지 고려해 `qwen3:1.7b`를 선택했습니다. 태그 이름과 실제 파라미터 수는 다릅니다. Ollama 메타데이터상 약 2.03B, Q4_K_M이며 다운로드 가중치는 약 1.359 GB입니다.

모델 태그와 크기는 [Ollama Qwen3 공식 라이브러리](https://ollama.com/library/qwen3/tags), 로컬 도구 호출 형식은 [Ollama 공식 tool calling 문서](https://docs.ollama.com/capabilities/tool-calling)를 기준으로 합니다. 이 모델 크기는 대학원 수학 설명 품질을 보증하지 않습니다.

Windows 포터블 패키지는 [공식 Ollama v0.40.16 배포](https://github.com/ollama/ollama/releases/tag/v0.40.16)를 사용했습니다. 현재 PC의 내장 GPU용 가속 런타임을 설치하지 않고 CPU 실행에 필요한 파일 약 84.7 MB를 추출했습니다. 실행 파일의 Windows Authenticode 서명 유효성을 확인합니다. 다운로드 원본 약 1.618 GB는 보존합니다.

| 위치 | 목적 |
|---|---|
| `data/tools/ollama/` | 포터블 CPU 실행 파일·런타임 |
| `data/tools/ollama-windows-amd64.zip` | 공식 다운로드 원본, 삭제하지 않음 |
| `data/models/` | Ollama 모델 가중치·매니페스트 |
| `data/tools/ollama.out.log`, `ollama.err.log` | 로컬 서버 시작 진단 |
| `data/local-evaluation-runs/` | 실제 로컬 모델의 격리 교과서 검증 |

이미 설치된 PC에서는 다시 다운로드할 필요가 없습니다. 새 환경 설치 명령은 다음과 같습니다.

```powershell
.\scripts\setup-ollama.ps1
```

압축파일과 모델만 약 3 GB이며 추가 실행·시험 저장 공간이 필요합니다. 기존 자료와 다운로드 파일을 이번 작업에서 삭제하지 않았습니다.

## 실행과 모드

```dotenv
AI_MODE=live
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
OLLAMA_NUM_CTX=8192
OLLAMA_NUM_PREDICT=1000
OLLAMA_TIMEOUT=240
ALLOW_EXTERNAL_AI=false
```

`OLLAMA_NUM_CTX`는 문맥 길이, `OLLAMA_NUM_PREDICT`는 요청당 생성 한도입니다. 지나치게 키우면 메모리 사용량·대기 시간이 늘어납니다. 한도에 걸린 미완성 응답은 완성된 설명으로 저장하지 않습니다. 작은 모델의 생각 출력을 끄고 실제 도구 이름·결과만 실행 로그에 표시합니다.

```powershell
.\scripts\start.ps1 -RestartOwned
```

이 명령은 Ollama 준비 후 ScholarPilot을 실행합니다. Ollama만 먼저 시작하려면 `scripts/start-ollama.ps1`을 사용하세요. 기본 모델 서버는 `http://127.0.0.1:11434`, ScholarPilot은 `http://127.0.0.1:8000`입니다. `GET /api/version`과 `/api/tags`는 모델 생성 없이 로컬 상태만 확인합니다.

`start-ollama.ps1`은 `OLLAMA_NO_CLOUD=1`, 단일 병렬 요청·단일 로드 모델을 지정합니다. 백엔드 어댑터도 루프백 HTTP 주소만 허용하고 클라우드 모델 태그를 거절합니다. 로컬 실패 시 OpenAI로 자동 전환하지 않습니다. 기존 `.env` API 키는 변경·출력할 필요가 없습니다.

## 도구 어댑터와 검증 범위

현재 기본값은 `OLLAMA_TOOL_FORMAT=json`입니다. 모델이 JSON 스키마에 맞춰 도구 이름과 인자를 생성하면 어댑터가 검증하여 기존 도구 실행기에 전달합니다. 작은 모델에서 네이티브 함수 인자 오류가 반복돼 이 명시적 행동 프로토콜을 사용합니다. `native`는 선택 가능한 별도 모드이며 자동 전환하지 않습니다. 기본 배치는 128, 요청 제한 시간은 600초입니다. 최종 JSON 어댑터의 실제 모델 학습 흐름은 아직 미검증입니다.

`backend/ollama_provider.py`는 기존 Agent의 메시지·함수 호출·함수 결과를 Ollama의 `/api/chat` 형식으로 변환하고, 모델 도구 호출을 기존 도구 실행기에 넘깁니다. 서버가 현재 페이지를 준비한 이벤트와 모델이 직접 선택한 도구 호출은 로그에서 구분해 평가해야 합니다. 도구 이름이 실행 로그에 있다는 사실만으로 자율적 단계 선택을 입증하지 않습니다.

형식이 잘못된 도구 호출·정의되지 않은 도구·빈 응답·잘린 응답·시간 초과는 오류로 처리합니다. 자동으로 유료 공급자를 호출하거나 미완료 결과를 성공으로 바꾸지 않습니다. 작은 모델이 도구 사용을 안정적으로 수행하는지는 실제 교과서 시나리오 결과로 판단해야 합니다.

## 실제 한국어 스모크 측정

`docs/local-smoke.json`에는 실제 로컬 모델의 짧은 베이즈 설명 요청이 있습니다.

- 전체 9.543초, 로드 5.085초, 생성 3.379초.
- 입력 36토큰, 생성 87토큰, 생성 구간 약 25.7토큰/초.
- 로드된 모델 약 1.886 GB, 측정 VRAM 0.
- 측정 직후 가용 RAM 약 0.30 GiB.

이는 CPU에서 짧은 한국어 문장이 생성됨을 확인합니다. 원문 검색·긴 수식 유도·도구 반복 호출 시간이나 설명 정확성 점수는 아닙니다. 현재 메모리 여유가 작아 운영체제 페이지 파일과 다른 앱의 영향이 클 수 있습니다.

## 실제 PDF와 학습 흐름의 격리 검증

사용자 서재·학습 기록에 시험 답안을 저장하지 않도록 별도 서버를 사용합니다. 등록된 책의 사본과 검색 인덱스를 새 디렉터리에 만들며 사용자 대화·이해도 기록은 복사하지 않습니다.

```powershell
.\.venv\Scripts\python.exe scripts/local_validation_server.py --port 8021
```

새 터미널에서 한 번에 하나씩 진행합니다. 아래 명령은 **실제 로컬 모델을 실행**하므로 CPU·메모리를 사용하지만 유료 API를 호출하지 않습니다.

```powershell
.\.venv\Scripts\python.exe scripts/try_local_scenario.py A
.\.venv\Scripts\python.exe scripts/try_local_scenario.py B
.\.venv\Scripts\python.exe scripts/try_local_scenario.py grade
.\.venv\Scripts\python.exe scripts/try_local_scenario.py C
.\.venv\Scripts\python.exe scripts/try_local_scenario.py D
```

A는 Bishop PDF 48페이지 설명, B는 같은 대화의 선수 개념·문제, grade는 오답 채점, C는 전체 서재 Quantization, D는 같은 대화의 후속 질문입니다. A→B→grade 순서를 지키세요. B가 문제 생성에 실패했다면 grade를 실행하지 않습니다. 서버 표시 경로 아래 `scenario-*.json`, `local-model-calls.json`으로 응답·도구·시간·토큰을 확인합니다. 이 보고서에는 교과서 발췌와 개인 질문이 있을 수 있으므로 공개 저장소에 올리지 마세요.

과거 저장소로 재시작하려면 `--resume data/local-evaluation-runs/<실행ID>`를 사용합니다. 스크립트는 해당 경로와 전용 표시 파일을 검증합니다. 각 실제 시나리오의 통과 여부는 [개발 상태](../DEVELOPMENT_STATUS.md)의 최종 검증 결과에 기록합니다. 이 문서의 명령 제공 자체가 시나리오 통과를 의미하지 않습니다.

## 정확도와 성능 확인 방법

AI의 식과 인쇄 PDF의 식을 대조하고 `scripts/check_learning_math.py`로 독립 계산 예제를 검사합니다. 검색된 원문의 책·PDF 페이지와 화면 출처 이동을 확인합니다. PTQ/QAT를 다루지 않는 책에 내용을 억지로 연결하면 실패로 기록합니다. 정답 제출 전에는 퀴즈 해설·정답이 노출되지 않아야 합니다.

시간은 첫 로드와 후속 생성, 검색과 모델 호출을 구분합니다. `local-model-calls.json`의 로드·생성 시간, 입력·출력 토큰과 `/api/ps`의 메모리·VRAM을 함께 봅니다. CPU 사용에서는 긴 문맥이 짧은 스모크보다 훨씬 느릴 수 있습니다. 작은 모델의 오류를 Mock 문장으로 대체해 성공으로 표시하지 않습니다.

실제 사용자 학습 효과, 수식 유도의 일반적 무오류, 모든 문장의 근거 일치를 입증하는 실험은 아직 없습니다. OCR·그림 이해·임베딩 검색도 별도 미구현입니다.
