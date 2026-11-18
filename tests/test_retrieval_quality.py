from concurrent.futures import ThreadPoolExecutor
from backend.agent import Agent,ChatRequest
from backend.database import one
from backend.learning import save_quiz,evaluate
from backend.retrieval import query_terms,search,_rank

def test_korean_particles_and_abbreviations():
    terms=query_terms('PTQ와 QAT의 차이')
    assert 'ptq' in terms and 'qat' in terms
    assert 'gradient' in query_terms('경사하강법 설명')
    assert 'conditional' in query_terms('조건부확률이란?')
    assert not query_terms('여기 설명해 줘')

def test_bibliography_is_ranked_below_equivalent_explanation():
    source={'text':'Backpropagation describes gradient calculation.','section':'Backpropagation','rank':-1,'page':2}
    reference={**source,'section':'Bibliography'}
    assert _rank(source,['backpropagation'],None)>_rank(reference,['backpropagation'],None)

def test_irrelevant_single_word_match_is_rejected(client,book):
    assert search('conditional optimization',[book['id']])==[]
    assert search('gradient descent',[book['id']])
    assert all(r['book_id']==book['id'] for r in search('probability',[book['id']],current_book_id=book['id']))

def test_concurrent_quiz_and_answer_are_idempotent(client,book):
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='test'))
    payload={'concept':'probability','kind':'choice','question':'Which answer?','choices':['yes','no'],'answer':'yes','explanation':'yes'}
    with ThreadPoolExecutor(max_workers=8) as pool:
        quizzes=list(pool.map(lambda _:save_quiz(agent.session_id,book['id'],payload),range(8)))
    assert len({q['id'] for q in quizzes})==1
    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts=list(pool.map(lambda _:evaluate(quizzes[0]['id'],agent.session_id,'yes'),range(8)))
    assert len({a['attempt_id'] for a in attempts})==1
    assert one('SELECT count(*) AS n FROM attempts')['n']==1
    assert one('SELECT total FROM mastery')['total']==1
    different=evaluate(quizzes[0]['id'],agent.session_id,'no')
    assert different['already_submitted'] and different['requested_answer_was_ignored']
    assert different['correct'] and one('SELECT count(*) AS n FROM attempts')['n']==1

def test_quiz_log_does_not_reveal_answer(client,book):
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='test'))
    source=agent.execute('get_current_page',{})[0]
    result=agent.execute('generate_quiz',{'concept':'probability','kind':'choice','question':'Choose one','choices':['secret-answer','wrong'],
        'answer':'secret-answer','explanation':'private rubric','source_ids':[source['id']]})
    assert 'answer' not in result
    event=agent.events[-1]
    assert event['input']['answer']=='[답안 제출 전 비공개]'
    assert 'private rubric' not in str(event)
    assert 'private rubric' not in one('SELECT input FROM events WHERE run_id=? AND tool=?',(agent.run_id,'generate_quiz'))['input']

def test_numeric_grading_does_not_use_contradictory_ai_explanation(client,book):
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='test'))
    quiz=save_quiz(agent.session_id,book['id'],{'concept':'numeric','kind':'numeric','question':'2+2','answer':'4','explanation':'2+2 is 4'})
    result=evaluate(quiz['id'],agent.session_id,'5',{'correct':True,'confidence':1,'explanation':'5 is correct'})
    assert not result['correct'] and result['explanation']=='2+2 is 4'

def test_exact_short_answer_does_not_use_contradictory_ai_explanation(client,book):
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='test'))
    quiz=save_quiz(agent.session_id,book['id'],{'concept':'short','kind':'short','question':'Answer?','answer':'correct','explanation':'correct rubric'})
    result=evaluate(quiz['id'],agent.session_id,'correct',{'correct':False,'confidence':1,'explanation':'wrong explanation'})
    assert result['correct'] and result['explanation']=='correct rubric'

def test_math_selection_warns_about_pdf_extraction(client,book):
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='수식 설명',selection='Conditional probability ='))
    result=agent.run()
    assert '원본과 대조' in result['text']

def test_selection_from_another_page_is_not_attributed_to_current_page(client,book):
    agent=Agent(ChatRequest(book_id=book['id'],page=1,message='쉽게 설명',selection='Gradient descent uses derivatives for optimization'))
    result=agent.run()
    assert '대조하지 못했습니다' in result['text']
    assert not result['quiz']
