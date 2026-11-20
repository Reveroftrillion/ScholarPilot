# ScholarPilot

PDF 교과서를 읽으면서 선택한 문장의 한국어 번역과 쉬운 설명을 요청하고 이어서 질문하는 로컬 프로그램입니다. AI 응답은 이 PC의 Ollama `qwen3:1.7b` 모델을 사용합니다. OpenAI API 키는 필요하지 않습니다.

## Windows에서 실행

Python, Node.js/npm, Git이 필요합니다. 프로젝트 폴더의 PowerShell에서 처음 한 번 실행합니다.

```powershell
.\scripts\setup.ps1
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
.\scripts\setup-ollama.ps1
.\.venv\Scripts\python.exe scripts/import_books.py Books
```

기존 `.env`는 덮어쓰지 마세요. Ollama 설치 스크립트는 실행 파일과 모델을 다운로드하므로 인터넷 연결과 충분한 저장 공간이 필요합니다. `import_books.py`는 `Books`의 PDF를 로컬 서재에 등록합니다.

이후 ` .\scripts\start.ps1`을 실행하고 브라우저에서 [http://127.0.0.1:8000](http://127.0.0.1:8000)을 엽니다. 종료할 때 실행 창에서 `Ctrl+C`를 누릅니다. 코드나 설정을 변경한 뒤 기존 서버가 실행 중이면 ` .\scripts\start.ps1 -RestartOwned`로 재시작할 수 있습니다.

## 사용법

서재에서 책을 열고 PDF 문장을 드래그한 다음 **한국어 번역** 또는 **쉽게 설명**을 누르세요. 선택 문장을 유지한 채 채팅에서 추가 질문을 할 수 있습니다. 답변의 실제 검색 출처를 누르면 해당 PDF 페이지로 이동합니다. 마지막으로 읽은 페이지와 대화는 로컬 기록에서 복원합니다. 서재의 교과서 추가 버튼으로 기존 책을 유지하면서 PDF를 추가할 수 있습니다.

채팅 영역의 크기는 상단 슬라이더로 조절합니다. **고급 기능**에서 심화 진단, 검색 범위, RAG 비교, Python 독립 수식 검산과 실행 로그를 사용할 수 있습니다. 독립 검산은 제한된 계산만 확인하며 원문 해석이나 일반적인 수학적 증명을 보장하지 않습니다.

생성형 AI의 번역과 설명은 **미검증**입니다. 작은 로컬 모델은 수식, 숫자, 개념 및 번역을 틀릴 수 있으므로 PDF 원문과 대조하세요. OCR과 그림 해석은 지원하지 않습니다. CPU 환경에서는 응답에 수 분이 걸릴 수 있습니다. 자세한 한계는 [로컬 검증 보고서](docs/LOCAL_VALIDATION.md)를 참고하세요.

## 데이터와 검증

`.env`, 서재 복사본, 검색 DB 및 학습 기록이 있는 `data/`는 Git에서 제외됩니다. 백업할 때는 서버를 종료하고 `data/` 전체를 별도 보관하세요. 현재 `Books/`의 PDF 두 권은 Git이 추적합니다. 저장소의 실제 공개 설정과 PDF 배포 권한을 확인하세요. Git에서 추적을 중단해도 과거 이력에는 파일이 남습니다.

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short
cd frontend
npm test
npm run build
```

추가 정보: [DEMO.md](DEMO.md), [구조](ARCHITECTURE.md), [로컬 AI](docs/LOCAL_AI.md).
