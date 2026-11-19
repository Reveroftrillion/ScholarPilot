"""SQLite lexical retrieval with bounded query expansion, ranking and deduplication.

This is not embedding or semantic search. Results retain the exact text and
page of the source chunk. Expansion is intentionally small and inspectable.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from .database import many, one

ALIASES = {
    '경사하강법':'gradient descent', '경사 하강법':'gradient descent',
    '베이즈':'bayes', '조건부확률':'conditional probability', '조건부 확률':'conditional probability',
    '양자화':'quantization', '역전파':'backpropagation', '편미분':'partial derivative',
    '확률':'probability', '최적화':'optimization', '주의 메커니즘':'attention mechanism',
    '어텐션':'attention', '트랜스포머':'transformer', '선형 회귀':'linear regression',
    '선형회귀':'linear regression', '메모리 병목':'memory bottleneck', '모델 최적화':'model optimization',
    '유병률':'prevalence', '양성 판정':'positive screening', '질병':'disease cancer',
    '연속값':'continuous target', '예측':'prediction', '입력':'input',
    '기저 함수':'basis functions', '다항식':'polynomial', '가우시안':'gaussian',
    '관측치':'data point', '가중치':'weights', '은닉층':'hidden units',
    '한 관측치씩':'stochastic gradient descent',
    '오차 신호':'error signal', '비선형':'nonlinear', '활성화 함수':'activation functions',
    '수치 정밀도':'numerical precision', '정밀도':'precision', '학습이 끝난 뒤':'post training',
    '메모리':'memory', '계산량':'computation', '특징 맵':'feature maps',
    '자기 주의':'self attention', '클라우드':'cloud',
}
STOP = {'the','and','of','to','is','a','in','it','for','this','that','what','how','does','are','with',
        'explain','please','describe','difference','between','compare','vs','versus','mechanism','mechanisms',
        '이해','설명','설명해','설명해줘','해주세요','못했','모르겠어요','이란','차이','차이점','무엇','무엇인가요',
        '여기','이거','이것','뭐야','현재','페이지','해줘','알려줘','알려','자세히','쉽게','어떻게','수식','예제'}
STOP.update({'why','can','its','still','use','uses','which','during','from','an','need','help',
             'should','be','what','when','where','would','could','do','we','you','our','their'})
SPECIAL = {
    'sample space':['sample space'],
    'basis functions':['basis functions','basis function'],
    'data movement':['data movement'],
    'simulating quantization':['simulating quantization','fake quantization','quantization-aware training'],
    'ptq': ['ptq','post-training quantization','post training quantization','post training quantisation'],
    'qat': ['qat','quantization-aware training','quantization aware training','quantisation aware training'],
    'backpropagation':['backpropagation','back-propagation','back propagation'],
    'conditioning':['conditioning','conditional probability','conditional probabilities'],
    'responsiveness':['responsiveness','latency','response time'],
}

def query_terms(query):
    query=unicodedata.normalize('NFKC',query).casefold()
    # English concepts frequently carry Korean particles ("Attention의").
    # Split the boundary before filtering instructions, rather than discarding
    # the entire meaningful English term.
    query=re.sub(r'([a-z0-9])(?=[가-힣])',r'\1 ',query)
    query=re.sub(r'([가-힣])(?=[a-z])',r'\1 ',query)
    for ko,en in sorted(ALIASES.items(),key=lambda pair:-len(pair[0])):
        query=query.replace(ko,' '+en+' ')
    special=[]
    for key,variants in SPECIAL.items():
        if any(re.search(r'(?<![a-z])'+re.escape(v)+r'(?![a-z])',query) for v in variants):
            special.extend(variants)
            if key=='conditioning':special.append('conditional')
            for v in variants:query=re.sub(r'(?<![a-z])'+re.escape(v)+r'(?![a-z])',' ',query)
    words=[w for w in re.findall(r'[\w]+',query) if len(w)>1 and w not in STOP]
    # Korean particles or instructions attached to translated English terms are
    # not meaningful evidence in English books. Preserve Korean-only searches.
    if special or any(re.search('[a-z]',w) for w in words):
        words=[w for w in words if re.search('[a-z0-9]',w) and not re.search('[가-힣]',w)]
    if special and set(words)<= {'quantization','quantisation','training','post','aware','와','의'}:
        words=[]
    terms=list(dict.fromkeys(special+words))[:24]
    return terms

def _normalized(text):
    return re.sub(r'[^\w]+',' ',unicodedata.normalize('NFKC',text).casefold()).strip()

def _rank(row, terms, page):
    text=_normalized(row['text']); section=_normalized(row['section'] or '')
    normalized=[_normalized(t) for t in terms]
    hits=[term for term in normalized if term and re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text)]
    coverage=len(hits)/max(1,len(normalized))
    # Specific multi-word phrases carry more weight than generic words.
    phrase=max([min(3,len(term.split())) for term in hits] or [0])
    section_hits=sum(bool(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',section)) for term in normalized if term)
    proximity=.10/(1+abs(row['page']-page)) if page else 0
    # Bibliographies often mention every keyword but rarely explain the idea.
    # Keep them available as fallbacks, while ranking explanatory sections first.
    reference_penalty=2.0 if re.search(r'\b(bibliography|references|reference list)\b',section) else 0
    # Dot leaders identify contents lists even in PDFs without a TOC section
    # label. A repeated table heading is weaker evidence than its explanation.
    contents_penalty=2.5 if len(re.findall(r'\.\s*\.\s*\.',row['text']))>=3 else 0
    heading_penalty=.9 if len(text.split())<12 and re.match(r'^(aspect|method|strategy|technique|comparison|attribute|metric)\b',text) else 0
    return phrase*.7 + coverage + min(section_hits,.5)*.3 + proximity - row['rank']*.015-reference_penalty-contents_penalty-heading_penalty

def _deduplicate(rows, limit):
    result=[]
    for row in rows:
        normalized=_normalized(row['text'])
        if any(r['book_id']==row['book_id'] and r['page']==row['page'] and
               SequenceMatcher(None,normalized,_normalized(r['text']),autojunk=False).ratio()>=.85 for r in result):
            continue
        result.append(row)
        if len(result)>=limit:break
    return result

def search(query, book_ids=None, page=None, limit=8, current_book_id=None):
    limit=max(1,min(limit,50))
    if book_ids is None:
        book_ids=[b['id'] for b in many("SELECT id FROM books WHERE status='ready' ORDER BY id")]
    book_ids=list(dict.fromkeys(book_ids))
    terms=query_terms(query)
    if not terms or not book_ids:return []
    if len(book_ids)>1:
        groups=[search(query,[bid],page if bid==current_book_id else None,limit,bid) for bid in book_ids]
        # Keep at least the best result from each matching book, but order those
        # by relevance rather than book ID. Remaining results compete globally.
        heads=sorted([g[0] for g in groups if g],key=lambda r:r['score'],reverse=True)
        remaining=sorted([r for g in groups for r in g[1:]],key=lambda r:r['score'],reverse=True)
        return _deduplicate(heads+remaining,limit)
    expression=' OR '.join('"'+t.replace('"','')+'"' for t in terms)
    rows=many('''SELECT c.*, b.title, bm25(chunks_fts) AS rank FROM chunks_fts
        JOIN chunks c ON c.id=chunks_fts.chunk_id JOIN books b ON b.id=c.book_id
        WHERE chunks_fts MATCH ? AND b.status='ready' AND c.book_id=? ORDER BY rank LIMIT 120''',
        (expression,book_ids[0]))
    # For a short multiword concept, a hit containing only "linear" or only
    # "regression" is often misleading. Require at least two distinct query
    # words; a missing hit is preferable to an unrelated citation.
    if 2<=len(terms)<=4 and all(' ' not in term and '-' not in term for term in terms):
        def enough_words(row):
            text=_normalized(row['text']+' '+(row['section'] or ''))
            return sum(bool(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text)) for term in terms)>=2
        rows=[row for row in rows if enough_words(row)]
    for row in rows:row['score']=_rank(row,terms,page)
    rows.sort(key=lambda row:row['score'],reverse=True)
    return _deduplicate(rows,limit)

def get_chunk(chunk_id):
    return one('SELECT c.*,b.title FROM chunks c JOIN books b ON b.id=c.book_id WHERE c.id=?',(chunk_id,))
