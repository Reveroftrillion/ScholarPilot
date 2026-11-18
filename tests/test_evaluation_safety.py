import sys
import pytest
from scripts import evaluate

def test_live_evaluation_requires_explicit_approval_and_budget(monkeypatch):
    monkeypatch.setattr(sys,'argv',['evaluate.py','--mode','live'])
    with pytest.raises(SystemExit,match='approve-paid-api'):evaluate.main()
    monkeypatch.setattr(sys,'argv',['evaluate.py','--mode','live','--approve-paid-api'])
    with pytest.raises(SystemExit,match='max-total-api-calls'):evaluate.main()
