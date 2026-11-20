"""Bounded, independent checks, never a general AI answer-quality score."""
import ast
import math
import operator
import re

OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow}


def unsupported_book_mentions(text,titles):
    """Conservative warning, not natural-language entailment verification.

    Even an absence disclosure can trigger review. Never silently accept a
    mentioned book merely because citation IDs point to a different book.
    """
    normalize=lambda s:re.sub(r'[\W_]+','',s.casefold())
    content=normalize(text);mentioned=[]
    for title in titles:
        stem=re.split(r'\s*\(\d{4}\)|\s+-\s+',title)[0]
        if len(normalize(stem))>=10 and normalize(stem) in content:mentioned.append(title)
    return mentioned

def arithmetic(expression):
    if len(expression)>200:raise ValueError('expression too long')
    tree=ast.parse(expression,mode='eval')
    if sum(1 for _ in ast.walk(tree))>60:raise ValueError('expression too complex')
    def calc(node):
        if isinstance(node,ast.Expression):return calc(node.body)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            if not math.isfinite(node.value) or abs(node.value)>1e12:raise ValueError('number out of bounds')
            return node.value
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            value=calc(node.operand);return -value if isinstance(node.op,ast.USub) else value
        if isinstance(node,ast.BinOp) and type(node.op) in OPS:
            left,right=calc(node.left),calc(node.right)
            if isinstance(node.op,ast.Pow) and (abs(right)>12 or abs(left)>1e6):raise ValueError('power too large')
            value=OPS[type(node.op)](left,right)
            if not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>1e12:raise ValueError('invalid result')
            return value
        raise ValueError('not a numeric expression')
    return calc(tree)

def _plain(text):
    for _ in range(12):
        new=re.sub(r'\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}',r'(\1)/(\2)',text)
        if new==text:break
        text=new
    for old,new in [('\\times','*'),('\\cdot','*'),('×','*'),('÷','/'),('\\div','/'),('\\left',''),('\\right',''),('\\approx','='),('≈','='),('^','**'),('\\%','/100'),('%','/100')]:text=text.replace(old,new)
    text=re.sub(r'\\[,;! ]','',text)
    return text.replace('{','(').replace('}',')').strip().rstrip('.,;')


def probability_checks(text):
    """Check numeric event assignments, not arbitrary continuous densities.

    Recognizes simple p(A), p(A,B), p(A|B) notation; unparsed mathematics stays
    unverified. A correct arithmetic substitution can still use the wrong
    probability (e.g. a joint probability as a likelihood).
    """
    values={}
    text=text.replace('\\mid','|').replace('\\left','').replace('\\right','')
    for match in re.finditer(r'[pP]\(([^()\n]{1,60})\)\s*=\s*([^\n$]*?)(?=(?:[,;]\s*[pP]\(|\n|\$|$))',text):
        name=re.sub(r'\s+','',match[1]);right=match[2].strip().rstrip('.,;')
        right=re.split(r'\s+[가-힣]',right)[0]
        final=right.rsplit('=',1)[-1].strip()
        if not re.fullmatch(r'[\d\s.()+*/-]+',final):continue
        try:values[name]=arithmetic(final)
        except (ValueError,ArithmeticError,SyntaxError):continue
    marginals={key:value for key,value in values.items() if '|' not in key and ',' not in key}
    def resolve(event):
        if event in marginals:return event
        choices=[name for name in marginals if name.split('=')[0]==event]
        return choices[0] if len(choices)==1 else event
    checks=[]
    for name,claimed in values.items():
        if name.count('|')!=1:continue
        a,b=map(resolve,name.split('|'));expected=None
        joint=values.get(a+','+b,values.get(b+','+a))
        if joint is not None and marginals.get(b,0)>0:expected=joint/marginals[b]
        reverse=values.get(b+'|'+a)
        if expected is None and reverse is not None and marginals.get(b,0)>0 and a in marginals:expected=reverse*marginals[a]/marginals[b]
        if expected is not None:
            checks.append({'kind':'conditional probability from supplied event values','expression':name,'computed':expected,'claimed':claimed,
                           'status':'pass' if math.isclose(expected,claimed,rel_tol=1e-4,abs_tol=1e-6) else 'fail'})
    return checks

def assess(text,question,source_ids):
    issues=[];checks=[]
    # An observed model example lists two bare joint-density values, then
    # incorrectly treats one observation's loss as proof of an optimum.
    # This is a bounded rejection of that malformed claim, not an optimizer.
    example=text.split('### 설명을 위한 예시',1)[-1]
    if (re.search(r'제곱\s*손실|squared\s*loss',example,re.I)
            and re.search(r'[pP]\(\s*x\s*,\s*t\s*\)\s*=\s*\d*\.?\d+\s*,\s*\d*\.?\d+',example)
            and re.search(r'최적\s*예측|optimal',example,re.I)):
        checks.append({'kind':'unsupported squared-loss optimum from incomplete joint distribution','status':'fail'})
        issues.append('예제의 결합분포에 대응하는 관측값이 없고, 개별 손실 계산만으로 최적 예측값을 단정했습니다. 기대 손실·최적성 결론을 확인하세요.')
    # A known extraction/generation error on the expected-loss page leaves
    # a differential in the variational derivative but drops its integral.
    for line in text.splitlines():
        compact=re.sub(r'\s+','',line)
        if ('E[L]' in compact and ('δ' in compact or '\\delta' in compact)
                and ('δf(' in compact or '\\deltaf(' in compact)
                and re.search(r'dt(?:[=$.,]|$)',compact)
                and '∫' not in compact and '\\int' not in compact):
            checks.append({'kind':'expected-loss derivative missing integral','status':'fail'})
            issues.append('기대 손실의 변분 미분식에서 적분 기호가 누락되었습니다. 원문 수식을 확인하세요.')
    probabilities=probability_checks(text);checks.extend(probabilities)
    if any(check['status']=='fail' for check in probabilities):issues.append('조건부확률의 값이 제시된 결합확률·주변확률과 일치하지 않습니다.')
    expressions=re.findall(r'\$\$([\s\S]*?)\$\$|(?<!\$)\$([^$\n]+)\$',text)
    regions=[a or b for a,b in expressions]
    for region in regions:
        parts=re.split(r'=|≈|\\approx',_plain(region))
        for left,right in zip(parts,parts[1:]):
            if not re.fullmatch(r'[\d\s.()+*/eE-]+',left.strip()) or not re.fullmatch(r'[\d\s.()+*/eE-]+',right.strip()):continue
            try:
                actual,claimed=arithmetic(left.strip()),arithmetic(right.strip())
                valid=math.isclose(actual,claimed,rel_tol=1e-6,abs_tol=1e-7)
                if not valid and ('\\approx' in region or '≈' in region) and re.fullmatch(r'\d*\.\d+',right.strip()):
                    valid=round(actual,len(right.strip().split('.')[1]))==claimed
                checks.append({'expression':left+' = '+right,'status':'pass' if valid else 'fail','computed':actual,'claimed':claimed})
                if not valid:issues.append('숫자 예제의 등식이 독립 계산 결과와 다릅니다.')
            except ArithmeticError:
                checks.append({'expression':left+' = '+right,'status':'fail'});issues.append('숫자 예제에 계산할 수 없는 식이 있습니다.')
            except (ValueError,SyntaxError):
                checks.append({'expression':left+' = '+right,'status':'unverified'})
                issues.append('수치 표기가 독립 검산기의 지원 범위를 벗어나 해당 등식을 검증하지 못했습니다.')
    canonical=re.sub(r'\s+','',text).replace('\\left','').replace('\\right','').replace('\\cdot','').replace('\\mid','|').replace('*','').replace('$','')
    canonical=re.sub(r'(?<=\))(?:은|는)(?=[pP]\()', '=',canonical)
    # A recurrent PDF extraction failure joins the numerator to the left-hand
    # conditional probability and silently discards the separate denominator.
    missing=r'[pP]\(([A-Za-z])\|([A-Za-z])\)=[pP]\(([A-Za-z])\|([A-Za-z])\)[pP]\(([A-Za-z])\)(?!\s*(?:/|\\over))'
    for a,b,c,d,prior in re.findall(missing,canonical):
        if (c,d,prior)==(b,a,a):
            checks.append({'kind':'Bayes missing denominator','status':'fail'})
            issues.append('역방향 조건부확률과 사전확률을 곱한 식에서 정규화 분모가 누락되었습니다.')
    pattern=r'[pP]\(([A-Za-z])\|([A-Za-z])\)=\\frac\{[pP]\(([A-Za-z])\|([A-Za-z])\)[pP]\(([A-Za-z])\)\}\{[pP]\(([A-Za-z])\)\}'
    for a,b,c,d,prior,denominator in re.findall(pattern,canonical):
        valid=(c,d,prior,denominator)==(b,a,a,b)
        checks.append({'kind':'Bayes symbol direction','status':'pass' if valid else 'fail'})
        if not valid:issues.append('베이즈 형태의 수식에서 조건 방향·사전확률·분모가 서로 맞지 않습니다.')
        if re.search(r'유도|deriv',question,re.I) and valid:
            joint={f'p({a},{b})',f'p({b},{a})'}
            forward=f'p({a}|{b})p({b})';reverse=f'p({b}|{a})p({a})'
            products=set()
            for region in regions:
                pieces=re.sub(r'\s+','',region).replace('P(','p(').replace('\\cdot','').split('=')
                if joint.intersection(pieces):products.update(pieces)
            if not {forward,reverse}<=products:issues.append('베이즈 결론을 반복하는 대신 결합확률의 두 표현을 연결하는 중간 단계가 필요합니다.')
            condition=bool(re.search(r'[pP]\('+re.escape(b)+r'\)\s*(?:(?:>|\\gt)\s*0|(?:\\ne(?:q)?|≠)\s*0)',text))
            if not condition:issues.append('베이즈 정리에서 분모가 양수라는 적용 조건이 빠졌습니다.')
    derivation=bool(re.search(r'유도|deriv',question,re.I))
    numerical=bool(re.search(r'숫자|계산 예제|numeric|numerical|worked example',question,re.I))
    if derivation and sum(region.count('=') for region in regions)<2:issues.append('요청한 수식 유도의 중간 등식이 충분히 제시되지 않았습니다.')
    if numerical and not any('expression' in check for check in checks):issues.append('요청한 숫자 예제의 대입·계산 결과를 독립 검증하지 못했습니다.')
    inline=re.findall(r'#source-([A-Za-z0-9_-]+)',text)
    if any(cid not in source_ids for cid in inline):issues.append('확인되지 않은 출처 링크가 답변에 포함되어 있습니다.')
    return {'status':'needs_review' if issues else 'limited_checks_passed','issues':list(dict.fromkeys(issues)),
            'math_checks':checks,'limits':'일부 산술·베이즈 표기·요청 요소만 검사합니다. 모든 유도·주장·원문 일치를 증명하거나 AI 품질 점수를 산출하지 않습니다.'}
