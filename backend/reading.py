"""Resolve the learner's actual PDF target before retrieval or generation."""
import json
import re
import pymupdf
from .database import one, many, data_path
from difflib import SequenceMatcher


def page_request(message):
    match = re.search(r'(?i)(?:\bpage\s*(\d+)|(?:PDF\s*)?(\d+)\s*(?:페이지|쪽|pages?\b))', message)
    if not match:
        return None
    number = int(match[1] or match[2])
    prefix=message[max(0,match.start()-20):match.start()]
    reference=match.group(0)
    if re.match(r'(?i)pdf\s*\d',reference) or re.search(r'(?i)\bpdf\s*$',prefix):
        basis='pdf'
    elif re.search(r'(?:인쇄|책|교재|printed)\s*(?:의\s*)?(?:페이지|쪽|번호)?\s*$',prefix,re.I):
        basis='printed'
    else:
        basis='pdf' if match[1] else 'unspecified'
    return number, basis


def previous_context(agent):
    rows = many("SELECT request,response FROM runs WHERE session_id=? AND id!=? ORDER BY rowid DESC LIMIT 6",
                (agent.session_id, agent.run_id))
    turns = []
    context = None
    for row in rows:
        request = json.loads(row['request'])
        response = json.loads(row['response'] or '{}')
        if context is None and response.get('reading_context'):
            context = response['reading_context']
        turns.append({'question': request['message'], 'page': response.get('reading_context', {}).get('page', request['page']),
                      'selection': response.get('reading_context', {}).get('selection', request.get('selection', ''))})
    return context, list(reversed(turns[:3]))


def task_for(request):
    if request.task != 'auto':
        return request.task
    if re.search(r'그림|피규어|도표|도식|\bfigure\b|\bdiagram\b', request.message, re.I):
        return 'figure'
    if re.search(r'번역|\btranslat', request.message, re.I):
        return 'translate'
    if re.search(r'자세|상세|짧|길게|수식|유도|예제|예시|\bdetail|\bderiv', request.message, re.I):
        return 'detail'
    return 'explain'


def selection_sources(rows, selection):
    normalize=lambda value:re.sub(r'\W+','',value.casefold())
    selected=normalize(selection)
    matched=[]
    for row in rows:
        text=normalize(row['text'])
        if not text:continue
        overlap=SequenceMatcher(None,selected,text,autojunk=False).find_longest_match().size
        if overlap>=max(12,min(len(selected),len(text))*.6):matched.append(row)
    return matched


def resolve(agent):
    r = agent.req
    old, turns = previous_context(agent)
    requested = page_request(r.message)
    new_selection=bool(r.selection and (not old or r.page!=old['page'] or r.selection!=old.get('selection','')))
    current_page=bool(re.search(r'이\s*페이지|현재\s*페이지|여기|this page',r.message,re.I))
    new_visible_page=bool(old and current_page and r.page!=old['page'])
    follow = bool(old and not new_selection and not new_visible_page and re.search(r'더|자세|짧|쉽게|다시|앞서|이전|방금|예제|예시|설명하라고|설명해|설명해\s*줘|explain|again', r.message, re.I))
    page = old['page'] if old and not new_visible_page else r.page
    selection = r.selection
    if selection:
        page = r.page
    elif follow and old:
        selection = old.get('selection', '')
    topic = old.get('topic', '') if old and follow else r.message
    basis = old.get('page_basis', 'pdf') if old and not new_visible_page else 'pdf'
    book = one('SELECT id,title,pages FROM books WHERE id=?', (r.book_id,))
    if not book:
        raise ValueError('현재 교과서를 찾을 수 없습니다.')
    with pymupdf.open(data_path()/'pdfs'/f"{r.book_id}.pdf") as pdf:
        if requested:
            number, basis = requested
            labels = pdf.get_page_numbers(str(number), only_one=False) if pdf.get_page_labels() else []
            if basis == 'unspecified':
                if old and old.get('requested_page') == number:
                    basis = old.get('page_basis', 'pdf')
                elif labels and any(p+1 != number for p in labels):
                    options = ', '.join(str(p+1) for p in labels)
                    agent.reading_notice = f'페이지 번호를 확인해 주세요. PDF {number}페이지와 인쇄 {number}쪽(PDF {options}페이지)은 서로 다릅니다. “PDF {number}페이지” 또는 “인쇄 {number}쪽”으로 지정해 주세요.'
                else:
                    basis = 'assumed_pdf'
            if not getattr(agent, 'reading_notice', None):
                if basis == 'printed':
                    if len(labels) != 1:
                        agent.reading_notice = '이 PDF에서 인쇄 페이지 번호를 하나로 확인하지 못했습니다. PDF 페이지 번호로 지정해 주세요.'
                    else:
                        page = labels[0]+1
                else:
                    page = number
                if not 1 <= page <= len(pdf):
                    agent.reading_notice = f'이 교과서는 PDF 1~{len(pdf)}페이지입니다. 범위 안의 페이지를 지정해 주세요.'
                    page = old['page'] if old else r.page
                if page != r.page or not selection:
                    selection = ''
                topic = r.message
        if not 1 <= page <= len(pdf):
            raise ValueError('현재 PDF 페이지 범위를 확인하세요.')
        printed = pdf[page-1].get_label() if pdf.get_page_labels() else None
    r.page, r.selection = page, selection
    agent.task = task_for(r)
    if old and r.task=='auto' and old.get('task')=='detail' and re.fullmatch(r'\s*(?:다시\s*)?설명(?:하라고|해\s*줘|해줘)[.!?\s]*',r.message):
        agent.task='detail'
    if agent.task=='figure' and old and old.get('page')==page:
        topic=old.get('topic',topic)
    pending=bool(getattr(agent,'reading_notice',None))
    if pending:
        basis=(old or {}).get('page_basis','pdf')
        topic=(old or {}).get('topic',r.message)
    agent.reading_context = {'book_id': r.book_id, 'page': page, 'printed_page': printed,
                             'page_basis': basis, 'selection': selection, 'topic': topic,
                             'task':agent.task,
                             'want_example':agent.task=='detail' and not re.search(r'예제\s*없이|예시\s*없이|without examples?',r.message,re.I) and bool(re.search(r'예제|예시|examples?',r.message,re.I) or (follow and (old or {}).get('want_example'))),
                             'requested_page': requested[0] if requested and not pending else None if new_selection or new_visible_page else (old or {}).get('requested_page')}
    agent.reading_turns = [turn for turn in turns if turn['page']==page] if follow else []
    agent.page_focus = bool(requested or selection or follow or current_page)
    # A restored learner target is data. No old AI answer becomes evidence.
    return agent.reading_context


def figure_notice(agent, rows):
    """Read actual captions; a text-only model must not infer visual contents."""
    with pymupdf.open(data_path()/'pdfs'/f"{agent.req.book_id}.pdf") as pdf:
        page = pdf[agent.req.page-1]
        captions = []
        for block in page.get_text('blocks', sort=True):
            text = block[4].strip()
            # A caption starts with a figure label; body references do not count.
            if re.match(r'^(?:Figure|Fig\.?|그림)\s*\d', text, re.I):
                captions.append(re.sub(r'\s+', ' ', text))
        agent.figure_context = {'visual_analysis': False, 'captions': captions,
                                'page_image_url': f'/api/books/{agent.req.book_id}/pages/{agent.req.page}/math-image'}
    label = f"PDF {agent.req.page}페이지"
    printed = agent.reading_context.get('printed_page')
    if printed:
        label += f' (인쇄 {printed}쪽)'
    text = f'{label}의 그림을 직접 해석하는 기능은 현재 지원하지 않습니다. Qwen3 8B는 텍스트 전용이므로 그림의 모양이나 관계를 추측하지 않았습니다.'
    if captions:
        text += '\n\n실제 페이지에서 추출한 그림 번호·캡션(이미지 분석 결과가 아닙니다):\n\n' + '\n\n'.join(captions)
        if len(captions) > 1:
            text += '\n\n그림이 여러 개입니다. 확인하려는 그림 번호를 지정해 주세요.'
    else:
        text += '\n\n이 페이지에서 그림 번호로 시작하는 캡션을 확인하지 못했습니다. 본문의 그림 참조만으로 그림이 있다고 단정하지 않습니다.'
    text += '\n\nPDF 원문에서 그림을 확인해 주세요. 텍스트와 캡션의 설명은 별도로 질문할 수 있습니다.'
    agent.cited_ids.update(row['id'] for row in rows if re.search(r'Figure|Fig\.|그림', row['text'], re.I))
    return text
