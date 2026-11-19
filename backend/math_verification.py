"""Bounded arithmetic/rational identities; never eval/sympify model strings."""
import ast
import re
from pydantic import BaseModel,Field,ConfigDict


class MathInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    formula:str=Field(default='',max_length=1000)
    source_confirmed:bool=False
    expression:str=Field(default='',max_length=240)
    comparison:str=Field(default='',max_length=240)
    bindings:dict[str,str]=Field(default_factory=dict,max_length=8)


def parse(expression,bindings=None):
    import sympy as s
    if len(expression)>240:raise ValueError('식은 240자 이내로 입력하세요.')
    tree=ast.parse(expression.replace('^','**'),mode='eval')
    if sum(1 for _ in ast.walk(tree))>48:raise ValueError('지원하는 식의 복잡도를 넘었습니다.')
    def bound(node):
        if isinstance(node,ast.Expression):return bound(node.body)
        if isinstance(node,ast.Name):return 1,1
        if isinstance(node,ast.Constant):return 0,1
        if isinstance(node,ast.UnaryOp):return bound(node.operand)
        if isinstance(node,ast.BinOp):
            a,na=bound(node.left);b,nb=bound(node.right)
            if isinstance(node.op,ast.Pow):
                if not isinstance(node.right,ast.Constant) or type(node.right.value)!=int or not 0<=node.right.value<=4:raise ValueError('정수 지수 0~4만 지원합니다.')
                degree,terms=a*node.right.value,na**node.right.value
            else:degree,terms=(max(a,b),na+nb) if isinstance(node.op,(ast.Add,ast.Sub)) else (a+b,na*nb)
            if degree>8 or terms>256:raise ValueError('대수 검증의 차수·전개 한도를 넘었습니다.')
            return degree,terms
        raise ValueError('지원하지 않는 수학 표현입니다.')
    bound(tree)
    divisions=[];symbols=set();bindings=bindings or {}
    def convert(node):
        if isinstance(node,ast.Expression):return convert(node.body)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            raw=ast.get_source_segment(expression.replace('^','**'),node)
            if not raw or len(raw)>20 or abs(float(raw))>1e9:raise ValueError('수치 범위를 넘었습니다.')
            return s.Rational(raw)
        if isinstance(node,ast.Name) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,19}',node.id):
            symbols.add(node.id)
            if len(symbols)>8:raise ValueError('기호는 8개까지 지원합니다.')
            if node.id in bindings:
                value=bindings[node.id]
                if not re.fullmatch(r'[+-]?(?:\d{1,10}(?:\.\d{1,12})?|\.\d{1,12})',value):raise ValueError('변숫값은 유한한 십진수로 입력하세요.')
                return s.Rational(value)
            return s.Symbol(node.id,real=True)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            value=convert(node.operand);return -value if isinstance(node.op,ast.USub) else value
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow)):
            if isinstance(node.op,ast.Pow):
                if not isinstance(node.right,ast.Constant) or type(node.right.value)!=int or not 0<=node.right.value<=4:raise ValueError('정수 지수 0~4만 지원합니다.')
                if any(isinstance(n,ast.Pow) for n in ast.walk(node.left)):raise ValueError('중첩 거듭제곱은 지원하지 않습니다.')
            a,b=convert(node.left),convert(node.right)
            if isinstance(node.op,ast.Div):
                if b==0:raise ValueError('분모가 0입니다.')
                divisions.append(b);return a/b
            if isinstance(node.op,ast.Add):return a+b
            if isinstance(node.op,ast.Sub):return a-b
            if isinstance(node.op,ast.Mult):return a*b
            if a==0 and b==0:raise ValueError('0의 0제곱은 확정하지 않습니다.')
            if b==0 and a.free_symbols:divisions.append(a)
            return a**int(b)
        raise ValueError('숫자·기호·사칙연산·정수 거듭제곱만 지원합니다. 함수·적분·행렬은 미검증입니다.')
    value=convert(tree)
    return value,divisions


def verify(payload):
    """Source confirmation is a human assertion, not mathematical proof."""
    data=payload.model_dump() if isinstance(payload,MathInput) else payload or {}
    result={'status':'not_supplied','source_confirmed':bool(data.get('source_confirmed')),
            'formula':data.get('formula',''),'checks':[],
            'scope':'입력한 유리식의 산술·대수 항등식만 검증합니다. PDF 일치·확률 해석·유도 가정은 자동 인증하지 않습니다.'}
    if not data:return result
    if not data.get('expression'):
        result.update(status='unverified',reason='확인한 식과 계산식을 입력하세요. 추출 수식은 확정하지 않았습니다.');return result
    try:
        import sympy as s
        value,denominators=parse(data['expression'],data.get('bindings'))
        conditions=[str(d)+' != 0' for d in denominators if d.free_symbols]
        result.update(expression=data['expression'],bindings=data.get('bindings',{}),conditions=conditions,latex=s.latex(value))
        if data.get('comparison'):
            other,divisions=parse(data['comparison'],data.get('bindings'))
            result['conditions']+= [str(d)+' != 0' for d in divisions if d.free_symbols]
            same=s.cancel(value-other)==0
            result.update(status='verified_identity' if same else 'failed',comparison=data['comparison'],equivalent=same)
        elif not value.free_symbols:
            if value.is_finite is not True:raise ValueError('유한한 계산 결과가 아닙니다.')
            if abs(value)>10**12:raise ValueError('계산 결과의 지원 범위를 넘었습니다.')
            result.update(status='verified_calculation',exact=str(value),value=float(value))
        else:result.update(status='unverified',reason='기호 값이나 비교할 식이 없어 참·거짓을 확정하지 않았습니다.')
    except (ValueError,SyntaxError,TypeError,ArithmeticError) as exc:result.update(status='failed',reason=str(exc))
    return result
