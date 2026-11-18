# ScholarPilot

로컬 PDF 서재와 대학원 전공서적 학습 Agent입니다. 기존 React·PDF.js·KaTeX 화면, FastAPI, PyMuPDF, SQLite FTS5 검색과 학습 기록을 유지하며, 기본 실제 AI 공급자를 **이 PC에서 실행하는 Ollama**로 변경했습니다.

현재 설치 모델은 `qwen3:1.7b`입니다. 로컬 한국어 생성은 확인했으며, 실제 교과서 전체 학습 흐름과 설명 품질의 검증 범위는 [개발 상태](DEVELOPMENT_STATUS.md)와 [로컬 AI 안내](docs/LOCAL_AI.md)를 확인하세요. Mock은 원문 발췌·상태 관리 확인용이며, 로컬 모델의 실제 생성과 구분합니다.

## 실행

처음 내려받았다면 의존성과 로컬 모델을 설치합니다. Python과 Node.js/npm이 필요합니다.

```powershell
git clone https://github.com/Reveroftrillion/ScholarPilot.git
cd ScholarPilot
.\scripts\setup.ps1
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
.\scripts\setup-ollama.ps1
```

교과서 PDF, 기존 학습 기록, `.env`, Ollama 실행 파일과 모델은 저장소에 포함하지 않습니다. 처음 실행하면 서재에서 본인이 보유한 PDF를 추가하세요. Ollama와 모델 설치에는 인터넷 연결과 수 GB의 저장 공간이 필요합니다.

```powershell
.\scripts\start.ps1
```

[http://127.0.0.1:8000](http://127.0.0.1:8000)을 엽니다. 스크립트는 Ollama를 먼저 시작하고 ScholarPilot을 실행합니다. 같은 프로젝트의 최신 서버가 이미 있으면 재사용합니다. 코드나 `.env` 변경 후에는 다음 명령을 사용하세요.

```powershell
.\scripts\start.ps1 -RestartOwned
```

다른 프로그램의 포트는 종료하지 않습니다. 필요하면 `-Port 8002`로 포트를 바꿉니다. [Health Check](http://127.0.0.1:8000/api/health)에서 실행 코드·디스크 코드, DB와 프런트엔드 빌드 상태를 확인할 수 있습니다. ScholarPilot 종료는 실행 창에서 `Ctrl+C`입니다. Ollama는 별도 로컬 프로세스여서 계속 실행될 수 있습니다.

## 로컬 AI 설정

기존 `.env`를 덮어쓰지 마세요. `.env`가 없을 때만 예제 파일을 복사합니다.

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

현재 기본 구성은 다음과 같습니다. **OpenAI API 키가 필요 없으며, 외부 유료 API를 호출하지 않습니다.**

```dotenv
AI_MODE=live
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
OLLAMA_NUM_CTX=8192
OLLAMA_NUM_PREDICT=1000
OLLAMA_NUM_BATCH=128
OLLAMA_TOOL_FORMAT=json
OLLAMA_TIMEOUT=600
ALLOW_EXTERNAL_AI=false
```

`AI_MODE=mock`은 AI 설명을 생성하지 않는 검증 모드입니다. `AI_MODE=live`와 `AI_PROVIDER=ollama`를 함께 지정해야 실제 로컬 모델을 사용합니다. 기존 OpenAI 구현은 남아 있지만 로컬 경로는 OpenAI를 대체 공급자로 호출하지 않습니다. `.env`에 남은 키 값은 출력하거나 보고서에 기록하지 않습니다.

현재 PC는 RAM 약 8 GB와 내장 GPU 구성입니다. 처음에는 브라우저 탭 등 다른 앱을 줄이고 한 번에 하나씩 질문하세요. 설치 모델, 저장 위치, 메모리 측정과 한계는 [로컬 AI 안내](docs/LOCAL_AI.md)에 있습니다.

현재 개발 스냅샷입니다. 실제 로컬 모델의 짧은 한국어 응답은 확인했지만, 첫 교과서 Agent 검증에서 부실한 설명과 잘못된 도구 인자가 발견됐습니다. JSON 스키마 어댑터로 수정한 후의 실제 모델·브라우저 전체 흐름은 아직 미검증입니다. 자동 테스트 통과는 설명 품질 검증을 의미하지 않습니다.

## 직접 확인하는 순서

1. 서재에서 Bishop 교과서를 열고 **PDF 48페이지**로 이동합니다. PDF 번호와 책에 인쇄된 페이지 번호는 다릅니다.
2. 베이즈 정리 문장이나 수식을 선택해 한국어 설명을 요청합니다. 선택문이 없으면 현재 책·페이지 내용이 전달됩니다.
3. 원문 발췌와 AI 설명을 구분하고, 출처를 눌러 원문 페이지로 이동합니다.
4. `아직 조건부확률이 이해가 안 돼. 선수 개념을 검색하고 확인 문제를 내줘.`라고 이어서 질문합니다.
5. 문제에 답하고 채점·해설·복습 추천을 확인합니다. 실행 로그에서 실제 도구 호출과 상태 변화를 확인할 수 있습니다.
6. 페이지를 새로고침해 책·페이지·대화·미제출 문제와 학습 기록의 복원을 확인합니다.
7. 전체 서재 검색에서 Quantization 또는 PTQ/QAT를 질문합니다. 책마다 해당 내용이 있는지 원문 출처로 확인합니다.

위 내용은 사용 순서입니다. 모든 단계의 실제 로컬 모델 성공을 보증하는 문구는 아니며, 완료 여부는 [개발 상태](DEVELOPMENT_STATUS.md)에 기록합니다. 소형 모델은 수식·숫자·출처를 틀릴 수 있으므로 PDF와 계산 검증을 함께 사용하세요. AI의 채점만으로 학습 이해도 향상을 입증하지 않습니다.

## 설치 및 개발

현재 Python 3.13, Node.js 24 환경을 사용합니다.

```powershell
.\scripts\setup.ps1
.\.venv\Scripts\python.exe scripts/import_books.py
```

현재 PC에는 공식 Windows Ollama 포터블 실행 파일과 모델이 준비돼 있습니다. 새 환경에 설치하려면 다음 스크립트를 사용합니다. 공식 압축파일 약 1.6 GB와 선택 모델 약 1.4 GB를 다운로드하므로 저장 공간과 네트워크를 먼저 확인하세요.

```powershell
.\scripts\setup-ollama.ps1
```

별도 개발 서버가 필요한 경우 백엔드와 프런트엔드를 각각 실행합니다.

```powershell
# 터미널 1
.\scripts\start-ollama.ps1
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 터미널 2
cd frontend
npm run dev
```

## 검증과 평가

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short
.\.venv\Scripts\python.exe scripts/evaluate_learning.py
.\.venv\Scripts\python.exe scripts/check_learning_math.py
.\.venv\Scripts\python.exe scripts/inspect_test_storage.py
cd frontend
npm test
npm run build
```

실제 두 교과서에서 확인한 24개 학습 평가 사례는 [학습 평가 기준](docs/LEARNING_EVALUATION.md), 이전 RAG·Agent 비교는 [AGENT_VS_RAG](docs/AGENT_VS_RAG.md), 측정 결과는 [평가 보고서](docs/EVALUATION_REPORT.md)에 있습니다. 키워드 검색 지표, Mock 상태 전이, 실제 모델의 설명 품질은 서로 다른 평가입니다.

브라우저 회귀 테스트는 사용자 학습 기록을 복사하지 않은 격리 QA 저장소에서 수행합니다. 기존 `scripts/browser_fixture.py --mode mock` 및 `--mode fixture`는 외부 AI를 호출하지 않는 화면·계약 검증입니다. `scripts/local_validation_server.py`는 실제 Ollama를 쓰는 별도 격리 서버입니다. 상세 실행과 한계는 [로컬 AI 안내](docs/LOCAL_AI.md)를 확인하세요.

## 데이터 보호와 한계

원본 사본·SQLite·추출문·학습 기록은 `data/`에 저장합니다. 백업하려면 서버 종료 후 전체 폴더를 복사하세요. 기존 `Books/` PDF와 사용자 학습 기록은 이번 로컬 전환에서 삭제하지 않습니다. `.env`, PDF, `Books/`, `data/`는 Git 제외 대상입니다.

시험 저장소·벤치마크·모델 다운로드 파일도 임의로 지우지 않습니다. `scripts/inspect_test_storage.py`는 용량을 조회하며 삭제하지 않습니다. 로컬 모델과 Ollama 설치물은 각각 `data/models`, `data/tools`에 있습니다.

OCR, 임베딩 검색, 그림 영역 해석과 복습 일정은 미구현입니다. FTS5는 키워드·한영 별칭 중심 검색입니다. PDF 수식 텍스트는 기호가 빠질 수 있으며, 소형 로컬 모델에는 추가 오답 위험이 있습니다. Windows WinError 10014 재현과 Vite 번들 크기 경고는 기존 환경의 알려진 한계입니다.

구조: [ARCHITECTURE.md](ARCHITECTURE.md). 코드 진단: [IMPLEMENTATION_AUDIT.md](docs/IMPLEMENTATION_AUDIT.md). 발표 순서: [DEMO.md](DEMO.md). 과거 OpenAI API 시도는 [LIVE_VALIDATION.md](docs/LIVE_VALIDATION.md)에 보존하며, 현재 실행 지침은 로컬 Ollama 기준입니다.
