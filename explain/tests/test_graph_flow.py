import pytest
from explain.graph_flow import ExplainQuizRouterGraph, FlowState
from backend.database import Database


@pytest.fixture
def graph_ctx(tmp_path):
    db_file = tmp_path / "graph_test.db"
    db = Database(f"sqlite:///{db_file}")
    # Insert test person
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO person (id, auth_id, name, dob_year, sex) VALUES ('p01', 'a01', 'Fatima', 1998, 'F')")
    conn.commit()
    conn.close()
    return ExplainQuizRouterGraph(database=db)


def test_graph_flow_explain_to_quiz_to_pass(graph_ctx):
    state = FlowState(
        person_id="p01",
        template_key="CARRIER_AR_SUMMARY",
        slots={"gene": "HBB", "condition_name": "Beta-thalassemia"},
        language="en",
    )

    # 1. Explain node
    state = graph_ctx.step_explain(state)
    assert state.step == "quiz"
    assert state.explanation_text is not None
    assert "HBB" in state.explanation_text

    # 2. Correct answers
    correct_answers = {
        "q1_carrier_meaning": "b",
        "q2_risk_vs_diagnosis": "a",
        "q3_same_gene_probability": "a",
        "q4_residual_risk": "b",
    }
    state = graph_ctx.step_quiz(state, correct_answers)
    assert state.teach_back_passed is True
    assert state.quiz_score == 100.0
    assert state.step == "route"

    # 3. Route node
    state = graph_ctx.step_route(state, base_tier="T0")
    assert state.assigned_tier == "T0"
    assert state.system_action == "self_serve_options_library"
    assert state.step == "completed"


def test_graph_flow_fail_twice_escalates_to_counsellor(graph_ctx):
    state = FlowState(
        person_id="p01",
        template_key="CARRIER_AR_SUMMARY",
        slots={"gene": "HBB", "condition_name": "Beta-thalassemia"},
        language="ar",
    )

    state = graph_ctx.step_explain(state)
    assert state.step == "quiz"

    # Bad answers (all incorrect)
    bad_answers = {
        "q1_carrier_meaning": "a",
        "q2_risk_vs_diagnosis": "b",
        "q3_same_gene_probability": "b",
        "q4_residual_risk": "a",
    }

    # First failed attempt -> allowed to retry
    state = graph_ctx.step_quiz(state, bad_answers)
    assert state.teach_back_passed is False
    assert state.quiz_score == 0.0
    assert state.teach_back_failed_twice is False
    assert state.step == "quiz"

    # Second failed attempt -> flags failed twice and moves to route
    state = graph_ctx.step_quiz(state, bad_answers)
    assert state.teach_back_passed is False
    assert state.teach_back_failed_twice is True
    assert state.step == "route"

    # Routing node: T0 escalates to T1 because teach-back failed twice!
    state = graph_ctx.step_route(state, base_tier="T0")
    assert state.assigned_tier == "T1"
    assert "TRI-T1-002" in state.fired_rule_ids
    assert state.system_action == "offer_counsellor_booking"
