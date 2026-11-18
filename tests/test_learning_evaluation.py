import json
from pathlib import Path
import pytest
from scripts.check_learning_math import main as check_math
from scripts.validate_learning_record import validate

def test_math_examples():
    check_math()

def test_learning_dataset_preserves_korean_utf8():
    root=Path(__file__).resolve().parents[1]
    cases=json.loads((root/'docs/learning-cases.json').read_text(encoding='utf-8'))
    assert cases[0]['question'].startswith('베이즈 정리')
    assert all('??' not in c['question'] for c in cases)
    assert all(any('가'<=char<='힣' for char in c['expected_elements']) for c in cases)

def test_record_needs_all_nine_scores_and_human_reviewer():
    record=json.loads((Path(__file__).resolve().parents[1]/'docs/learning-record-example.json').read_text(encoding='utf-8'))
    assert validate(record)
    record['evaluation']['scores']['grounding']=2
    with pytest.raises(ValueError,match='reviewer'):validate(record)
