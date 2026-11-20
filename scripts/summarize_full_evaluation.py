"""Publish aggregate metrics/review notes, never textbook excerpts or user history."""
import argparse
import collections
import json
import statistics
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();root=a.directory
    attempts=rows(root/'full-results.jsonl')+rows(root/'full-browser.jsonl')+rows(root/'extra-results.jsonl')
    baseline=list({r['id']:r for r in attempts}.values())
    reruns=rows(root/'full-rerun.jsonl');ledger=json.loads((root/'local-model-calls.json').read_text(encoding='utf-8'))
    generated=[r for r in ledger if r.get('metrics',{}).get('generated_tokens',0)>0]
    reviews=json.loads((root/'manual-review.json').read_text(encoding='utf-8'))
    manifest=json.loads((root/'full-manifest.json').read_text(encoding='utf-8'))
    bypage={(r.get('source',{}).get('book_id',r.get('request',{}).get('book_id')),r.get('source',{}).get('page',r.get('page'))) for r in baseline}
    bypage={pair for pair in bypage if pair[0] and pair[1]}
    browser=list({r['id']:r for r in rows(root/'full-browser.jsonl')}.values())
    durations=sorted(r['elapsed'] for r in baseline)
    lines=['# ScholarPilot 전체 시스템 실사용 평가','',
      '전체 교과서를 완독 검증했다는 뜻이 아니다. 두 책의 여러 장에서 실제 페이지를 표본 평가했다. 유효한 JSON, 출처 ID, needs_review 상태는 의미 정확성의 통과 판정이 아니다.','',
      '## 환경과 재현','',
      '- Windows / Ryzen 5 7500F / RAM 16GB / RTX 5070 12227 MiB, 드라이버 621.01',
      '- Ollama 0.40.16 / qwen3:8b / 문맥 4096 / 로컬 FastAPI + React / 외부 유료 호출 0',
      '- 기준 커밋: f4bbda96b1e6300d92d327123739e06954f522bb',
      '- 평가 DB는 scripts/local_validation_server.py로 만든 책·검색 인덱스 복사본. 사용자 세션·답안은 복사하지 않았다.',
      '- scripts/full_system_evaluation.py → scripts/full_system_browser.cjs → 실패 사례 재실행. 브라우저는 실제 PDF text layer 선택과 번역 버튼, 출처 클릭, 새로고침을 사용한다.',
      '- 원문·요청·응답·출처·시간·메모리는 ignored data/local-evaluation-runs/ 아래에만 저장한다. 이 보고서에는 원문 대량 발췌가 없다.','',
      '## 실행 규모','',
      f'- 고유 사례 {len(baseline)}개, 기록된 초기/추가/브라우저 시도 {len(attempts)}개, 별도 API 재실행 {len(reruns)}개',
      f'- 실제 생성 토큰이 확인된 Ollama 호출 {len(generated)}회 / provider 시도 기록 {len(ledger)}회. Mock·캐시 결과 없음.',
      f'- 서로 다른 책·PDF 페이지 {len(bypage)}개; 고유 브라우저 시나리오 {len(browser)}개',
      '- API 기본 평가와 후반부 보완은 기준 코드로 실행했다. 브라우저는 초기 실패 후 일부 수정본에서 이어 실행했으며 원본 시도도 남겼다. 아래 유형별 상태는 API 기본 결과와 브라우저의 마지막 시도이며 전체 의미 정확도나 동일 버전 성공률이 아니다.',
      f'- 시간(전체 사례): 중앙값 {statistics.median(durations):.2f}초, p95 {durations[min(len(durations)-1,int(len(durations)*.95))]:.2f}초, 최대 {max(durations):.2f}초',
      '- 시간은 서버/브라우저 처리 시간을 포함한다. 서로 다른 작업의 시간을 모델 성능 비교로 해석하지 않는다.','',
      '| 유형 | 실행 | 상태 분포 |','|---|---:|---|']
    for kind,count in collections.Counter(r['kind'] for r in baseline).items():
        states=collections.Counter(r.get('response',{}).get('status','browser_error' if r.get('browser_error') else 'unknown') for r in baseline if r['kind']==kind)
        lines.append(f'| {kind} | {count} | {dict(states)} |')
    lines+=['','## 책·페이지 분포','','| 책 | PDF 페이지 | 인쇄 페이지 | 목차상 절 |','|---|---:|---|---|']
    for m in manifest:
        label='Bishop' if 'Bishop' in m['book'] else 'ML Systems'
        lines.append(f'| {label} | {m["page"]} | {m["printed"]} | {m["section"]} |')
    lines+=['','## 원문 직접 대조 검토','','모델 자기평가를 사용하지 않았다. 각 행의 판단은 평가자가 원문과 실제 응답을 대조한 제한적 검토이며, 일반적인 증명을 인증하지 않는다. 번역 검토 행에는 문장 순서·절의 논리·기호 보존 여부를 기록한다.','',
            '| 사례 | 판정 | 원문·논리·계산 대조 결과 |','|---|---|---|']
    for r in reviews:lines.append(f'| {r["id"]} | {r["assessment"]} | {r["notes"]} |')
    notes=root/'conclusions.json'
    conclusions=json.loads(notes.read_text(encoding='utf-8')) if notes.exists() else {}
    for heading in ['기능별 결과와 한계','공통 오류와 수정 전후','수식 독립 검산','최종 남은 문제','회귀 테스트']:
        lines+=['','## '+heading,'',conclusions.get(heading,'평가 진행 중. 아직 완료 판정을 내리지 않았다.')]
    Path('docs/FULL_SYSTEM_EVALUATION.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    summary=['# ScholarPilot 실사용 평가 요약','',f'고유 사례 {len(baseline)}개, 별도 API 재실행 {len(reruns)}개, 실제 Ollama 생성 {len(generated)}회, 책·페이지 {len(bypage)}개, 고유 브라우저 {len(browser)}개.','',conclusions.get('요약','평가 진행 중.'),'','상세 결과: [FULL_SYSTEM_EVALUATION.md](FULL_SYSTEM_EVALUATION.md)']
    Path('docs/FULL_SYSTEM_EVALUATION_SUMMARY.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    print(json.dumps({'cases':len(baseline),'generated_calls':len(generated),'pages':len(bypage),'browser':len(browser)}))


if __name__=='__main__':main()
