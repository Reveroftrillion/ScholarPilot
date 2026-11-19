"""Server-issued key provenance. Model confidence never certifies a key."""
import re
from .quality import arithmetic

SYNONYMS={'conditional probability':{'조건부확률','conditional probability'},
          'joint probability':{'결합확률','동시확률','joint probability'},
          'gradient descent':{'경사하강법','gradient descent'},
          'quantization':{'양자화','quantization','quantisation'}}


def source_key(payload,sources):
    # Certify only literal source clozes, explicitly labelled recall practice.
    # Conceptual model questions remain unverified even with a real citation.
    answer=payload['answer'];question=payload['question']
    if not re.fullmatch(r'[A-Za-z][A-Za-z -]{2,60}',answer):return {'status':'unverified','measurement':'수식·수치 또는 복원되지 않은 기호는 원문 용어 회상 정답으로 인증하지 않습니다.'}
    norm=lambda v:re.sub(r'\s+',' ',v).strip().casefold()
    for source in sources:
        text=source['text']
        if len(text)>1200 or len(answer)<3 or norm(answer) not in norm(text):continue
        cloze=re.sub(re.escape(answer),'____',text,flags=re.I)
        if norm(question)==norm(cloze):
            aliases=list(SYNONYMS.get(answer.casefold(),{answer}))
            return {'status':'verified_source_recall','source_id':source['id'],'aliases':aliases,
                    'measurement':'원문 용어 회상. 개념 이해·수식 유도 진단이 아닙니다.'}
    return {'status':'unverified','measurement':'AI가 생성한 개념 문제. 정답·해설의 원문 타당성 미확인'}


def numeric_quiz(review,source_ids,concept):
    if review.get('status')!='verified_calculation' or not review.get('source_confirmed'):
        raise ValueError('원문 대조 확인과 독립 계산을 먼저 완료하세요.')
    return {'concept':'계산 연습 · '+concept[:120],'kind':'numeric',
            'question':'확인한 식의 계산 연습입니다. 다음 값은 얼마인가요?\n'+review['expression']+'\n입력값: '+', '.join(k+'='+v for k,v in review.get('bindings',{}).items()),
            'answer':str(review['value']),'explanation':'Python 독립 계산: '+review['expression']+' = '+review['exact'],
            'source_ids':source_ids,'tolerance':.001,
            '_verification':{'status':'verified_calculation','expression':review['expression'],
                'bindings':review.get('bindings',{}),
                'measurement':'입력한 식의 계산 능력. 변수의 확률 의미나 베이즈 정리 이해를 인증하지 않습니다.'}}
