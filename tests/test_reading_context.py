"""Routing/persistence contracts; fixture replies do not assess model quality."""
import json
import pymupdf
import pytest
from backend.agent import Agent, ChatRequest
from backend.database import one
from tests.test_reliable_learning import ReliableFixture


SELECTION = ('The probability p(X=xi) concerns a particular value xi.\n'
             'p(X) is a distribution; p(xi) is its value at xi.')


@pytest.fixture
def reading_book(client):
    pdf = pymupdf.open()
    pdf.new_page().insert_text((50, 50), 'Preface: introductory notes on probability and learning.')
    pdf.new_page().insert_text((50, 50), 'A different page discussing classification and training examples.')
    page = pdf.new_page()
    page.insert_text((50, 50), SELECTION)
    page.insert_text((50, 110), 'Expected squared loss is minimized by the conditional mean of the target.')
    page.insert_text((50, 180), 'Figure 3.1 A regression function and its conditional distribution.')
    page.draw_rect(pymupdf.Rect(50, 205, 180, 255))
    page.insert_text((50, 290), 'Figure 3.2 A second diagram with a distinct caption.')
    page.draw_line(pymupdf.Point(50, 315), pymupdf.Point(180, 345))
    page = pdf.new_page()
    page.insert_text((50, 50), 'Index\nconditional mean, 3\nloss function, 3\nrandom variable, 3')
    page.insert_text((50, 130), 'This body paragraph refers to Figure 9.9 elsewhere; it is not a caption.')
    pdf.set_page_labels([{'startpage': 0, 'prefix': 'i'},
                         {'startpage': 1, 'style': 'D', 'firstpagenum': 1}])
    content = pdf.tobytes()
    pdf.close()
    response = client.post('/api/books', files={'file': ('reading.pdf', content, 'application/pdf')})
    assert response.status_code == 201, response.text
    return client.get('/api/books').json()[0]


def run(book, message, provider=None, **extra):
    provider = provider or ReliableFixture()
    result = Agent(ChatRequest(book_id=book['id'], page=extra.pop('page', 1), message=message, **extra), provider).run()
    assert result['status'] != 'error', result
    return result, provider


def model_request(provider):
    return next(json.loads(message['content']) for message in provider.context
                if isinstance(message, dict) and message.get('role') == 'user'
                and message.get('content', '').startswith('{') and 'book_id' in message['content'])


def test_explicit_pdf_page_is_read_directly_instead_of_index_search(client, reading_book, monkeypatch):
    def unexpected_search(*args, **kwargs):
        raise AssertionError('A page address must not be sent to lexical search')
    monkeypatch.setattr('backend.retrieval.search', unexpected_search)
    result, provider = run(reading_book, 'PDF 3페이지 설명해 줘')
    assert result['reading_context']['page'] == 3
    assert result['reading_context']['printed_page'] == '2'
    assert result['sources'] and {source['page'] for source in result['sources']} == {3}
    assert 'PDF 3페이지' in result['text']
    assert not any(event['tool'].startswith('search_') for event in result['events'])
    assert model_request(provider)['page'] == 3
    assert 'Expected squared loss' in json.dumps(provider.context)


def test_bare_page_number_requests_clarification_when_printed_page_differs(client, reading_book):
    result, provider = run(reading_book, '3쪽 설명해 줘')
    assert not provider.calls
    assert 'PDF 3페이지' in result['text']
    assert '인쇄 3쪽(PDF 4페이지)' in result['text']
    assert '확인' in result['text']
    repeated, again = run(reading_book, '3쪽 설명해 줘', session_id=result['session_id'])
    assert not again.calls
    assert '인쇄 3쪽(PDF 4페이지)' in repeated['text']


def test_explicit_printed_page_uses_pdf_labels_not_search_or_fixed_offset(client, reading_book):
    from backend.reading import page_request
    assert page_request('PDF 3페이지 (인쇄 2쪽) 설명')==(3,'pdf')
    assert page_request('PDF3페이지 설명')==(3,'pdf')
    assert page_request('인쇄 2쪽 (PDF 3페이지) 설명')==(2,'printed')
    result, provider = run(reading_book, '인쇄 2쪽 설명해 줘')
    assert result['reading_context']['page_basis'] == 'printed'
    assert result['reading_context']['page'] == 3
    assert result['reading_context']['printed_page'] == '2'
    assert model_request(provider)['page'] == 3
    assert 'PDF 3페이지' in result['text'] and '인쇄 2쪽' in result['text']


def test_reconstructed_followup_retains_target_and_selection_without_ai_answer(client, reading_book):
    first, _ = run(reading_book, '쉽게 설명해 줘', page=3, selection=SELECTION)
    provider = ReliableFixture()
    follow = Agent(ChatRequest(book_id=reading_book['id'], page=1,
                              message='너무 짧아. 수식과 예제까지 자세히 설명해 줘',
                              session_id=first['session_id']), provider).run()
    assert follow['status'] != 'error', follow
    assert follow['reading_context']['page'] == 3
    assert follow['reading_context']['selection'] == SELECTION
    assert follow['reading_context']['topic'] == first['reading_context']['topic']
    request = model_request(provider)
    assert request['page'] == 3 and request['selection'] == SELECTION
    assert request['_reading_task'] == 'detail'
    assert first['text'] not in json.dumps(provider.context, ensure_ascii=False)
    restored = json.loads(one('SELECT response FROM runs WHERE id=?', (follow['id'],))['response'])
    assert restored['reading_context'] == follow['reading_context']
    again, _ = run(reading_book, '설명하라고', session_id=follow['session_id'])
    assert again['reading_context']['page'] == 3
    assert again['reading_context']['selection'] == SELECTION
    assert again['task'] == 'detail'
    assert again['reading_context']['want_example'] is True


def test_figure_request_reports_real_captions_and_blocks_text_model_guessing(client, reading_book):
    result, provider = run(reading_book, 'PDF 3페이지 그림 설명해 줘')
    assert not provider.calls
    assert result['task'] == 'figure'
    assert result['figure_context']['visual_analysis'] is False
    assert len(result['figure_context']['captions']) == 2
    assert 'Figure 3.1' in result['text'] and 'Figure 3.2' in result['text']
    assert '직접 해석하는 기능은 현재 지원하지 않습니다' in result['text']
    assert '여러 개' in result['text']
    missing, _ = run(reading_book, 'PDF 4페이지 그림 설명해 줘')
    assert missing['figure_context']['captions'] == []
    assert '캡션을 확인하지 못했습니다' in missing['text']


def test_translation_retains_entire_selected_formula_lines_and_task(client, reading_book):
    result, provider = run(reading_book, '한국어 번역', page=3, selection=SELECTION, task='translate')
    assert result['translation_source'] == SELECTION
    assert result['reading_context']['selection'] == SELECTION
    request = model_request(provider)
    assert request['selection'] == SELECTION
    assert request['page'] == 3 and request['_reading_task'] == 'translate'
    assert 'p(X=xi)' in json.dumps(provider.context)
    assert all('제외했습니다' not in message.get('output', '') for message in provider.context
               if isinstance(message, dict))


def test_translation_without_selected_original_asks_for_scope_without_generation(client, reading_book):
    result, provider = run(reading_book, '한국어 번역', task='translate')
    assert not provider.calls
    assert '번역할 원문을 선택' in result['text']
    assert '페이지 전체' in result['text']


def test_new_selection_on_another_page_replaces_stale_topic_and_page_hint(client, reading_book):
    first,_=run(reading_book,'PDF 3페이지 설명해 줘')
    selected='A different page discussing classification and training examples.'
    result,provider=run(reading_book,'쉽게 설명',page=2,selection=selected,session_id=first['session_id'])
    assert result['reading_context']['page']==2
    assert result['reading_context']['topic']=='쉽게 설명'
    assert result['reading_context']['requested_page'] is None
    assert not any(message.get('content','').startswith('Previous learner context')
                   for message in provider.context if isinstance(message,dict))
    visible,_=run(reading_book,'이 페이지 설명해 줘',page=2,session_id=first['session_id'])
    assert visible['reading_context']['page']==2
    assert {source['page'] for source in visible['sources']}=={2}


def test_observed_expected_loss_errors_keep_hard_warnings():
    from backend.quality import assess
    missing='δE[L]/δf(x) = 2{f(x)-t}p(x,t) dt = 0'
    proper='δE[L]/δf(x) = 2∫{f(x)-t}p(x,t) dt = 0'
    assert any(check['status']=='fail' for check in assess(missing,'',[])['math_checks'])
    assert not assess(proper,'',[])['issues']
    unsupported=('### 설명을 위한 예시\n제곱 손실은 (2.5-3)^2=0.25입니다. '
                 'p(x, t) = 0.5, 0.5일 때 기대 손실은 0.25이며 최적 예측 함수입니다.')
    assert any(check['status']=='fail' for check in assess(unsupported,'',[])['math_checks'])
    individual='제곱 손실의 개별 관측 예시: $(2.5-3)^2=0.25$. 이 계산만으로 최적성을 판단할 수 없습니다.'
    assert not assess(individual,'',[])['issues']


def test_relative_pages_and_comparison_use_both_actual_pages(client,reading_book):
    following,_=run(reading_book,'다음 페이지 내용을 요약해 줘',page=2)
    assert following['reading_context']['page']==3
    compared,provider=run(reading_book,'이전 페이지와 지금 페이지의 차이는?',page=3)
    assert compared['reading_context']['comparison_pages']==[2,3]
    assert {source['page'] for source in compared['sources']}=={2,3}
    assert any(message.get('content','').startswith('Comparison PDF page DATA') for message in provider.context if isinstance(message,dict))
    compared,_=run(reading_book,'다음 페이지와 지금 페이지의 차이는?',page=2)
    assert compared['reading_context']['comparison_pages']==[3,2]
    assert {source['page'] for source in compared['sources']}=={2,3}
    boundary,provider=run(reading_book,'다음 페이지와 비교해 줘',page=4)
    assert not provider.calls and '마지막' in boundary['text']
    boundary,provider=run(reading_book,'이전 페이지 설명해 줘',page=1)
    assert not provider.calls and '범위' in boundary['text']


def test_table_and_axes_requests_never_invoke_text_model(client,reading_book):
    for message in ['이 표를 해석해 줘','그래프의 x축과 y축을 설명해 줘']:
        result,provider=run(reading_book,message,page=3)
        assert not provider.calls and result['task']=='figure'
        assert result['figure_context']['visual_analysis'] is False


def test_pdf_glyph_variants_do_not_require_one_contiguous_match(client,reading_book):
    selected=SELECTION.replace('probability','probabi1ity').replace('distribution','distributi0n')
    result,provider=run(reading_book,'한국어 번역',page=3,selection=selected,task='translate')
    assert result['translation_source']==selected and provider.calls


def test_unsupported_notation_is_not_a_proven_arithmetic_error():
    from backend.quality import assess
    unsupported=assess('$2 e^{-2*1} = 2 e^{-2}$','',[])
    assert not any(c['status']=='fail' for c in unsupported['math_checks'])
    assert any(c['status']=='unverified' for c in unsupported['math_checks'])
    assert any(c['status']=='fail' for c in assess('$1/0 = 2$','',[])['math_checks'])


def test_missing_search_evidence_does_not_cite_the_current_page(client,reading_book):
    result,provider=run(reading_book,'유니콘 연금술을 설명해 줘',page=3)
    assert not provider.calls
    assert result['sources']==[]
    assert '확인하지 못했습니다' in result['text']
