import json
import math
import re
import uuid
from .database import db, one, many

def concept(book_id, name):
    name = name.strip()[:160]
    with db() as c:
        c.execute('INSERT OR IGNORE INTO concepts(id,book_id,name) VALUES(?,?,?)', (uuid.uuid4().hex,book_id,name))
    return one('SELECT * FROM concepts WHERE book_id=? AND name=?', (book_id,name))['id']

def save_quiz(session_id, book_id, payload):
    with db() as c:
        # Serialize simultaneous submissions for one session without a schema
        # migration or modifying old user records.
        c.execute('BEGIN IMMEDIATE')
        session=c.execute('SELECT book_id FROM sessions WHERE id=?',(session_id,)).fetchone()
        if not session or session['book_id']!=book_id:raise ValueError('세션과 교과서가 일치하지 않습니다.')
        existing=c.execute('SELECT q.id FROM quizzes q LEFT JOIN attempts a ON a.quiz_id=q.id WHERE q.session_id=? AND a.id IS NULL ORDER BY q.rowid DESC LIMIT 1',(session_id,)).fetchone()
        if existing:
            qid=existing['id']
        else:
            name=payload['concept'].strip()[:160]
            c.execute('INSERT OR IGNORE INTO concepts(id,book_id,name) VALUES(?,?,?)',(uuid.uuid4().hex,book_id,name))
            cid=c.execute('SELECT id FROM concepts WHERE book_id=? AND name=?',(book_id,name)).fetchone()['id']
            qid=uuid.uuid4().hex
            c.execute('INSERT INTO quizzes(id,session_id,concept_id,payload) VALUES(?,?,?,?)', (qid,session_id,cid,json.dumps(payload,ensure_ascii=False)))
            c.execute("INSERT OR IGNORE INTO mastery(concept_id) VALUES(?)", (cid,))
        c.execute("UPDATE sessions SET state='awaiting_answer' WHERE id=?", (session_id,))
    return public_quiz(qid)

def public_quiz(qid):
    row = one('SELECT * FROM quizzes WHERE id=?', (qid,))
    if not row:
        raise ValueError('퀴즈를 찾을 수 없습니다.')
    payload = json.loads(row['payload'])
    return {'id':qid, **{k:v for k,v in payload.items() if k not in ('answer','accepted','explanation')}}

def normalize(value):
    return re.sub(r'[\W_]+', '', str(value).casefold())

def grade(payload, answer):
    if payload['kind'] == 'numeric':
        try:
            value = float(answer)
            correct = math.isfinite(value) and math.isclose(value,float(payload['answer']),rel_tol=0,abs_tol=payload.get('tolerance',.001))
        except ValueError:
            correct = False
        uncertain = False
    else:
        correct = normalize(answer) in {normalize(a) for a in [payload['answer'], *payload.get('accepted',[])]}
        uncertain = payload['kind']=='short' and not correct
    cause = None if correct else ('표현이 다른 단답형: 자동 판단 불확실' if uncertain else ('계산 과정 확인' if payload['kind']=='numeric' else '개념 또는 선수 지식 복습'))
    return {'correct':correct,'uncertain':uncertain,'answer':payload['answer'], 'explanation':payload['explanation'],'cause':cause,
            'next_action':'다음 개념으로 진행' if correct else ('수동으로 정답과 비교하세요. 이해도는 낮추지 않았습니다.' if uncertain else '원문과 선수 개념을 다시 읽고 재진단하세요.')}

def evaluate(quiz_id, session_id, answer, assessment=None):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        q=c.execute('SELECT * FROM quizzes WHERE id=? AND session_id=?',(quiz_id,session_id)).fetchone()
        if not q:raise ValueError('이 세션의 퀴즈가 아닙니다.')
        old=c.execute('SELECT * FROM attempts WHERE quiz_id=?',(quiz_id,)).fetchone()
        if old:
            return {**json.loads(old['feedback']),'attempt_id':old['id'],'concept_id':q['concept_id'],
                    'already_submitted':True,'requested_answer_was_ignored':normalize(answer)!=normalize(old['answer'])}
        payload=json.loads(q['payload'])
        result=grade(payload,answer)
        if assessment and payload['kind']=='short' and result['uncertain']:
            confidence=assessment.get('confidence',0)
            if assessment.get('correct') is not None and confidence>=.85:
                result['correct']=assessment['correct']
                result['uncertain']=False
            result['confidence']=confidence
            result['grading']='AI 의미 평가 (오판 가능)' if not result['uncertain'] else 'AI 의미 평가 불확실'
        # Never replace a deterministic answer key with a contradictory model
        # explanation; a model can be wrong even when it claims high confidence.
        agrees=assessment and assessment.get('correct')==result['correct']
        if agrees and assessment.get('explanation'):
            result['explanation']=assessment['explanation']
            if not result['correct']:result['cause']=assessment.get('cause') or result['cause']
        if not result['uncertain']:
            result['next_action']='다음 개념으로 진행' if result['correct'] else '부족한 개념을 복습하고 다시 진단하세요.'
        aid=uuid.uuid4().hex
        c.execute('INSERT INTO attempts(id,quiz_id,answer,correct,uncertain,feedback) VALUES(?,?,?,?,?,?)',
                  (aid,quiz_id,answer,int(result['correct']),int(result['uncertain']),json.dumps(result,ensure_ascii=False)))
        c.execute("UPDATE sessions SET state='ready' WHERE id=?", (session_id,))
        _update_mastery(c,q['concept_id'])
    return {**result,'attempt_id':aid,'concept_id':q['concept_id']}

def _update_mastery(c,concept_id):
    all_rows = c.execute('SELECT a.*,q.payload FROM attempts a JOIN quizzes q ON q.id=a.quiz_id WHERE q.concept_id=? AND a.uncertain=0 ORDER BY a.created,a.rowid', (concept_id,)).fetchall()
    # Repeated versions of the same question are one piece of evidence.
    unique = {}
    for row in all_rows:
        key=normalize(json.loads(row['payload'])['question'])
        unique.pop(key,None)
        unique[key] = row
    rows = list(unique.values())
    correct = sum(r['correct'] for r in rows)
    streak = 0
    for r in reversed(rows):
        if not r['correct']: break
        streak += 1
    status = '이해 완료' if streak>=3 and correct/max(len(rows),1)>=.8 else ('복습 필요' if rows and not rows[-1]['correct'] else '학습 중')
    c.execute('INSERT INTO mastery(concept_id,correct,total,streak,status) VALUES(?,?,?,?,?) ON CONFLICT(concept_id) DO UPDATE SET correct=excluded.correct,total=excluded.total,streak=excluded.streak,status=excluded.status,updated=CURRENT_TIMESTAMP', (concept_id,correct,len(rows),streak,status))
    return dict(c.execute('SELECT * FROM mastery WHERE concept_id=?',(concept_id,)).fetchone())

def update_mastery(concept_id):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        return _update_mastery(c,concept_id)

def history(book_id):
    return many('SELECT c.name,c.book_id,m.* FROM mastery m JOIN concepts c ON c.id=m.concept_id WHERE c.book_id=? ORDER BY m.updated DESC', (book_id,))

def recommend(book_id):
    rows = history(book_id)
    review = [r for r in rows if r['status']=='복습 필요']
    return {'action':'review' if review else 'continue','topics':review or [r for r in rows if r['status']=='학습 중'],
            'message':'복습 필요 개념을 먼저 확인하세요.' if review else '현재 절의 예제를 풀고 다음 절로 진행하세요.'}
