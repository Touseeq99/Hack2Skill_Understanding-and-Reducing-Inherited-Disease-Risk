from eval.run_eval import run_evaluations


def test_promptfoo_safety_evaluations():
    assert run_evaluations() is True

