# RTX 5070 로컬 모델 비교 — 2026-11-20

현재 데스크톱에서 기본 모델을 `qwen3:8b`로 선택했다. 한국어 번역과 PTQ/QAT 답변의 완성도가 1.7B보다 나았고, GPU에 전부 올라간 상태의 설명은 약 3초였다. 수학 설명의 정확성이 검증됐다는 뜻은 아니다. 1.7B, PDF 및 사용자 학습 기록은 보존했다. GitHub push는 하지 않았다.

## 실행 환경과 GPU 복구

- Ryzen 5 7500F 6코어/12스레드, 시스템 RAM 15.59GiB(장착 16GB).
- NVIDIA RTX 5070, VRAM 12,227MiB, 드라이버 621.01.
- 공식 Windows Ollama 0.40.16: `data/tools/ollama/ollama.exe`.
- 기존 모델 디렉터리 `data/models/`를 그대로 사용. 두 모델 모두 Q4_K_M.
- 문맥 4096, 동시 실행 1, 로드 모델 1, Q8 KV 캐시, temperature 0.2, thinking 비활성화. 기존 기본 설명 경로의 출력 상한은 480토큰이다.

기존 설치 스크립트는 압축파일의 `lib/ollama/` 바로 아래 파일만 풀어 CUDA 하위 디렉터리를 누락했다. 복구 전 짧은 1.7B 생성에서 `ollama ps`는 `100% CPU`, API의 `size_vram`은 0이었다. 같은 공식 압축파일의 CUDA 12/13 라이브러리를 복구하고 경로·명령·포트 소유권을 확인한 프로젝트 Ollama만 재시작했다. 설치 스크립트도 런타임 전체 트리를 풀도록 수정했다.

공식 문서에서도 [RTX 5070 지원](https://github.com/ollama/ollama/blob/main/docs/gpu.mdx)과 [Windows 포터블 GPU 런타임](https://github.com/ollama/ollama/blob/main/docs/windows.mdx)을 확인했다. 이번 실행 로그의 실제 백엔드는 CUDA 13, compute capability 12.0이었다.

| 실제 관측 | qwen3:1.7b | qwen3:8b |
|---|---:|---:|
| `ollama ps` PROCESSOR | 100% GPU | 100% GPU |
| GPU 계층 | 29/29 | 37/37 |
| CUDA 가중치 버퍼 | 1,123.71MiB | 4,643.78MiB |
| CUDA KV 버퍼(4096) | 238MiB | 306MiB |
| API 모델 VRAM(실행 메모리 포함) | 1.453GB | 5.221GB |
| nvidia-smi 전체 VRAM 최대 | 3,103MiB | 6,722MiB |
| 샘플링한 GPU 사용률 최대 | 90% | 96% |

전체 VRAM과 GPU 사용률에는 기존 화면·다른 앱도 포함된다. 모델 VRAM은 Ollama API로 별도 확인했다. 8B의 모든 계층이 GPU에 있었고 메모리 부족 또는 CPU 계층 오프로딩은 관찰되지 않았다. 더 긴 문맥과 다른 동시 작업까지 보장하는 결과는 아니다.

## 동일 요청 비교

사용자 학습 기록을 복사하지 않은 별도 DB에서 기존 ScholarPilot Agent, 검색, JSON 스키마와 독립 검산 경로를 실행했다. 세 질문은 모델마다 한 번씩 수행했다. 최초 CUDA 준비 시간의 영향을 확인하기 위해 A만 각 모델에 한 번 더 실행하고 원시 로컬 응답을 기록했다. 자동 재시도나 외부 API 호출은 없었다.

비교 전 두 모델에 공통으로 번역 지시 충돌을 수정했다. 이전에는 번역 요청 뒤에 스키마와 마지막 메시지가 개념 설명만 요구했다. 번역 요청에는 번역 전용 지시를 사용하며 출처 검증, JSON 검증, 수학 검산과 미검증 표시는 유지한다.

| 요청 | 1.7B 시간 / 입력·출력 토큰 | 8B 시간 / 입력·출력 토큰 |
|---|---|---|
| A: Bishop PDF 48p 영어 선택문 한국어 번역 | 3.36초 / 1165·106, 내용 검증 실패 | 6.01초 / 1165·112, 번역 반환 |
| B: Bayes 조건부·역방향·결합확률과 0.12/0.4 예시 | 1.80초 / 1238·208 | 3.10초 / 1238·236 |
| C: Systems PDF 534p PTQ/QAT 시점·재학습·정확도·비용 비교 | 0.90초 / 1197·151 | 2.58초 / 1197·198 |

A는 재측정값이며 모델 전환 로딩 약 2.46초/4.00초를 포함한다. B/C는 모델이 로드된 요청이다. 최초 A는 CUDA 준비와 로딩으로 43.74초/15.31초였다. 이를 정상 응답 속도나 8B의 속도 우위로 해석하지 않는다. CUDA 준비 후 순수 생성 속도는 1.7B 약 266~287토큰/초, 8B 약 94~98토큰/초였다. 출력 길이가 달라 토큰 수와 실제 요청 시간을 함께 기록했다. 각 값은 적은 횟수의 관측이며 평균 성능 보장이 아니다.

### A: 번역

공통 선택문:

> Instead, we may simply write p(X) to denote a distribution over the random variable X, or p(xi) to denote the distribution evaluated for the particular value xi, provided that the interpretation is clear from the context.

1.7B는 두 실행 모두 JSON의 text에 영어 원문을 그대로 넣었다. JSON 구조는 맞았지만 한국어 내용 검증에서 거절됐다. 8B는 요약 대신 한국어 문장으로 번역하고 두 표기와 문맥 조건을 보존했다. 다만 “특정 값에서 분포를 평가한 값”을 “특정 값에 대한 분포”로 옮겨 엄밀성이 부족했다. 원문의 기호가 포함된 번역은 기존 수학 가드에 따라 미검증 초안으로 표시된다.

### B: 베이즈와 계산

1.7B는 조건부확률·역방향 조건부확률·결합확률의 기본 뜻은 구분했으나 요청한 비율 예시를 설명하지 않았다. 8B도 기본 뜻은 설명했지만 “조건의 확률 0.4”를 “조건부확률 0.4”라고 잘못 표현했고, 분모의 사건을 명확히 지정하지 않은 채 비율을 p(X|Y)라고 했다. 모델의 베이즈·수식 설명이 검증됐다고 볼 수 없다.

두 모델에서 동일하게 사용한 Python 독립 검산 `joint/condition`, `joint=0.12`, `condition=0.4`는 정확히 `3/10 = 0.3`을 반환했다. 이는 모델의 산술 능력이나 확률 해석을 증명하는 결과가 아니다. AI 수식 설명은 미검증 초안으로 남겼다.

### C: PTQ와 QAT

1.7B는 PTQ만 설명하고 QAT를 빠뜨렸다. 8B는 PTQ가 학습 후 적용되며 재학습을 요구하지 않는다는 점과, QAT가 학습 중 양자화를 고려하여 정확도를 유지하려 한다는 점을 구분했다. 다만 비용 비교와 QAT의 양자화 효과 모사는 충분히 설명하지 않았다. 비교의 완성도는 좋아졌지만 전문적인 설명 정확성을 보장하지 않는다.

### 출처와 보존

세 요청의 검색 근거는 DB의 책·페이지·청크 정보와 실제 PDF 텍스트에 모두 일치했다. 성공한 응답의 미해결 인용 ID는 0개였다. B는 Bishop PDF 48/51p, C는 Systems PDF 534p를 사용했다. 출처가 실제로 존재한다는 확인과 모델 문장의 의미가 근거에 부합한다는 평가는 별개다.

원시 요청·응답·토큰·GPU 샘플은 Git에서 제외된 `data/local-evaluation-runs/7098fad9152842fab7e5812eb8a51969/`의 `gpu-comparison.json`, `gpu-translation-warm.json`에 보존했다. 사용자 서재와 학습 DB를 삭제하거나 덮어쓰지 않았다.

## 최종 설정과 검증

`OLLAMA_MODEL=qwen3:8b`, `OLLAMA_NUM_CTX=4096`, `AI_MODE=live`, `AI_PROVIDER=ollama`, `ALLOW_EXTERNAL_AI=false`. `.env`의 다른 값은 보존했고 키는 출력하거나 커밋하지 않았다. 설정 예제와 기본값도 일치시켰다. 기존 1.7B로 돌아가려면 `.env`의 모델 태그만 바꾼 뒤 재시작한다.

기존 백엔드 154개, 프론트엔드 12개 테스트 및 TypeScript/Vite 빌드를 통과했다. 기존 번들 크기 경고와 FastAPI TestClient의 의존성 폐기 예정 경고는 남아 있다.

Edge 실제 브라우저의 별도 격리 서버에서 PDF 선택 → 8B 번역 → 쉬운 후속 설명 → Python 독립 검산 → 출처 페이지 이동 → 새로고침 복원을 확인했다. 원문 검색은 8개 결과를 반환했고 JavaScript 오류는 없었다. 실제 모델 호출은 2회였으며 외부 유료 호출은 0회였다. 이 브라우저 점검의 데이터는 `data/local-evaluation-runs/c6b8a8335c054b398b4c5adce0c5aacf/`에 보존했다. 사용자 학습 DB에는 시험 대화를 추가하지 않았다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
# 설정이나 코드를 바꾼 뒤 기존 프로젝트 서버를 재시작할 때
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -RestartOwned
```

브라우저 주소는 `http://127.0.0.1:8000`이다. 기존 외부 API 금지와 미검증 표시를 유지하며 새 모델에서도 원문 대조가 필요하다.
