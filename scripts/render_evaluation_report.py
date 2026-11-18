"""Build the local evaluation table from reproducible JSON results."""
import json
import statistics
from pathlib import Path

root=Path(__file__).resolve().parents[1]
docs=root/'docs'
def load(name):return json.loads((docs/name).read_text(encoding='utf-8'))
before=load('retrieval-before.json');after=load('retrieval-after.json')
evaluation=load('agent-evaluation.json')['results']
perf_before=load('performance-before.json');perf=load('performance.json')
browser=load('browser-performance.json');restart=load('restart-test.json');port=load('port-conflict.json')

lines=['# ScholarPilot 로컬 평가 보고서','',
       '## 범위와 한계','',
       '실제 교과서의 검색은 두 PDF와 인덱스를 읽기만 하여 평가했다. 관련성은 질문별 수동 지정 용어군이 청크 본문 또는 절 제목에 등장하는지에 대한 **대리 지표**다. 인간의 정답 레이블, 의미 이해도, 학습 효과 또는 AI 설명 품질을 측정하지 않는다. PDF 원문은 결과 파일에 저장하지 않았다.',
       '', '검색 전후는 동일한 12개 질문·동일한 인덱스·동일한 평가 코드다. 측정은 각각 1회이며 캐시와 부하가 다르므로 검색 시간의 변화는 성능 향상으로 단정할 수 없다.',
       '', '## 실제 PDF 검색', '', '| 지표 | 변경 전 | 변경 후 |', '|---|---:|---:|']
for label,key,denominator in [
    ('첫 결과의 용어 기준 관련','top1_proxy_hits','case_count'),
    ('상위 8개에서 모든 목표 용어군 발견','all_groups_found_at_8','case_count'),
    ('용어 기준 관련 결과','proxy_relevant_results','returned_results'),
    ('PDF 원문 및 해당 페이지와 일치','source_text_verified','returned_results'),
    ('동일 책·페이지의 유사 중복','duplicate_results',None),
    ('검색 중앙값 ms (단일 측정)','median_ms',None),
    ('검색 최댓값 ms (단일 측정)','max_ms',None)]:
    vals=[]
    for r in (before,after):
        value=r['metrics'][key]
        if denominator:value=f"{value}/{r.get(denominator,r['metrics'].get(denominator))}"
        vals.append(value)
    lines.append(f'| {label} | {vals[0]} | {vals[1]} |')
lines += ['',f"검색 범위 확인: 전 {before['metrics']['all_scope_checks_passed']}, 후 {after['metrics']['all_scope_checks_passed']}; 없는 용어의 빈 결과: 전 {before['metrics']['no_result_correct']}, 후 {after['metrics']['no_result_correct']}.",
          '첫 결과와 용어군 발견, 중복 제거가 개선됐다. 용어 기준 관련 결과 비율은 79/88에서 85/96으로 약간 낮아졌다. 이 지표는 줄바꿈·하이픈 표현을 놓치고 문맥의 적절성을 판단하지 못하므로, 관련 없는 결과의 실제 비율로 단정하지 않는다.',
          '', '| 질문 | 전: 첫 결과 / 용어군 / 중복 | 후: 첫 결과 / 용어군 / 중복 | 후 검색 ms |', '|---|---|---|---:|']
for b,a in zip(before['cases'],after['cases']):
    lines.append(f"| {a['query']} | {b['top1_proxy_relevant']} / {b['all_term_groups_found']} / {b['duplicate_count']} | {a['top1_proxy_relevant']} / {a['all_term_groups_found']} / {a['duplicate_count']} | {a['elapsed_ms']} |")
lines += ['', '각 행의 상세 페이지·청크 ID와 기준 용어는 `retrieval-before.json`, `retrieval-after.json`에서 확인할 수 있다. 한국어 확장은 제한된 사전 방식이며 모르는 표현은 검색되지 않을 수 있다.',
          '', '## Baseline RAG와 Agentic Learning: 오프라인 제어 흐름', '',
          '같은 12개 질문과 두 자체 제작 PDF를 사용했다. Agent의 추가 질문·오답 제출·중복 제출은 자동으로 이어졌으며 Baseline은 첫 응답만 처리했다. 시간은 서로 다른 단계 수를 포함하므로 모델 또는 학습 효과의 비교가 아니다.',
          '', '| 지표 | Baseline | Agent |', '|---|---:|---:|']
groups={key:[r for r in evaluation if r['strategy']==key] for key in ('baseline','agent')}
def field(strategy,key):
    rows=groups[strategy]
    count=sum(r[key] is True for r in rows)
    eligible=sum(r[key] is not None for r in rows)
    return f'{count}/{eligible}' if eligible else '해당 없음'
for label,key in [('질문별 원문 용어군 발견','retrieval_proxy_relevant'),('질문별 출처 청크·PDF 페이지 일치','source_metadata_correct'),
                  ('미제출 퀴즈 세션 복원','quiz_restored'),('오답 후 학습 상태 갱신','wrong_answer_mastery_updated'),
                  ('복습 추천','review_recommended'),('동일 답안 중복 저장 방지','duplicate_attempt_prevented')]:
    lines.append(f'| {label} | {field("baseline",key)} | {field("agent",key)} |')
for label,fn in [
    ('도구 실행 성공 / 실행',lambda r:f"{sum(x['tool_successes'] for x in r)}/{sum(x['tool_calls'] for x in r)}"),
    ('첫 응답 중앙값 초',lambda r:f"{statistics.median(x['initial_elapsed_seconds'] for x in r):.3f}"),
    ('전체 단계 중앙값 초',lambda r:f"{statistics.median(x['workflow_elapsed_seconds'] for x in r):.3f}"),
    ('외부 API 호출',lambda r:sum(x['api_calls'] for x in r)),
    ('모델 토큰',lambda r:sum(x['tokens'] for x in r))]:
    lines.append(f'| {label} | {fn(groups["baseline"])} | {fn(groups["agent"])} |')
lines += ['', 'Agent의 검색·선수 개념·퀴즈·평가·복습 도구 실행과 저장만 확인한 결과다. 실제 모델의 개념 진단·설명·채점 품질이나 학습자의 성취 향상은 아직 평가하지 않았다. 동일 데이터로 추후 실제 API 비교를 하려면 명시적 유료 호출 승인과 호출 상한이 필요하다.',
          '', '## 실제 PDF 처리와 안정성', '', '| 항목 | 측정 결과 |', '|---|---:|']
for b in perf['books']:lines.append(f"| {b['pages']}쪽 교과서 최초 인덱싱 | {b['index_seconds']}초 |")
lines += [f"| 656쪽 재인덱싱 전 / 후 | {perf_before['first_book_reindex_seconds']} / {perf['first_book_reindex_seconds']}초 |",
          f"| 새 책 추가·기존 책 재인덱싱 후 다른 책 청크 수 보존 | {perf['original_book_chunk_counts_stable_after_add']} / {perf['original_book_chunk_counts_stable_after_reindex']} |",
          f"| 동시 검색 | {perf['concurrent_queries_with_results']}/{perf['concurrent_queries']}회, {perf['concurrent_seconds']}초 |",
          f"| SQLite 무결성 / 외래 키 오류 | {perf['sqlite_integrity']} / {perf['foreign_key_errors']} |",
          f"| 청크 / FTS 행 수 | {perf['chunks']} / {perf['fts_rows']} |",
          f"| 사용자 책 메타데이터 변경 없음 | {perf['user_book_metadata_unchanged']} |",
          f"| Edge PDF 페이지 132 전환 (1회) | {browser['page_transition_ms']}ms |",
          f"| 서버 프로세스 재시작 후 책·페이지 / 퀴즈 복원 | {restart['book_and_page_restored']} / {restart['quiz_restored']} |",
          f"| 타 프로그램 포트 소유자 보호 | {port['foreign_listener_not_stopped']} |"]
lines += ['', '인덱싱 시간은 각 1회이며 디스크 캐시·부하에 영향을 받는다. 재인덱싱 전후의 트랜잭션 방식 변경은 반복적인 FTS 삭제 조회를 줄인다. 읽기 동시성 시험과 테스트용 동시 퀴즈 제출 시험을 수행했으며 장시간 부하 시험은 아니다.',
          '', 'Windows WinError 10014가 테스트 서버 초기화에서 재현됐다. 원인은 확인되지 않았고 동일 오류에만 횟수 제한 재시도를 적용했다. 다른 에러에는 재시도하지 않는다.',
          '', '## 재현', '', '```powershell',
          '.\\.venv\\Scripts\\python.exe scripts/evaluate_retrieval.py --output docs/retrieval-after.json',
          '.\\.venv\\Scripts\\python.exe scripts/evaluate.py',
          '.\\.venv\\Scripts\\python.exe scripts/benchmark_local.py',
          '.\\.venv\\Scripts\\python.exe scripts/port_conflict_probe.py',
          '.\\.venv\\Scripts\\python.exe scripts/render_evaluation_report.py',
          '```', '', '검색 평가는 사용자 책을 읽기만 한다. Agent와 인덱싱 성능 평가는 새 `data/evaluation-runs/`, `data/benchmarks/` 격리 저장소에 생성되며 사용자 기록을 변경하지 않는다. 실행마다 새 저장소가 생긴다.',
          '', '추후 같은 질문과 자체 제작 PDF로 유료 실제 모델을 평가하려면 `.env` 설정 후 사용자가 명시적으로 `scripts/evaluate.py --mode live --approve-paid-api --max-total-api-calls N`을 실행한다. 호출 상한을 지정해도 실제 비용과 품질은 모델 및 계정 조건에 따라 달라진다. 이번 평가에서는 실행하지 않았다.', '']
(docs/'EVALUATION_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print('Wrote docs/EVALUATION_REPORT.md')
