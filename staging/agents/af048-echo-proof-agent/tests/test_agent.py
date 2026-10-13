import pytest
from agent import run

@pytest.mark.parametrize("task", ["hello", "  hello  ", "left\tright", "first\nsecond", "こんにちは 🌱", "e\u0301", "é"])
def test_run_prefixes_nonblank_input_without_changing_it(task):
    assert run(task) == "Echo: " + task

@pytest.mark.parametrize("task", [None, 7, [], {}, ""])
def test_run_rejects_non_string_and_empty_inputs(task):
    with pytest.raises(ValueError):
        run(task)

@pytest.mark.parametrize("task", [" ", "\t\n", "\u2003\u00a0"])
def test_run_rejects_whitespace_only_inputs(task):
    with pytest.raises(ValueError):
        run(task)
