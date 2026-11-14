"""promptfoo custom Python provider.
Interfaces promptfoo test evaluations with the platform's explanation pipeline and intent classifier.
"""

from typing import Dict, Any
from explain.pipeline import pipeline
from backend.intent_classifier import intent_classifier


def _ensure_eval_person_exists():
    try:
        conn = pipeline.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM person WHERE id = 'p_eval'")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO person (id, auth_id, name, language, literacy_pref, dob_year, sex, pregnancy_status)
                VALUES ('p_eval', 'auth_eval', 'Eval Person', 'ar', 'standard', 1998, 'F', 0)
            """)
            conn.commit()
        conn.close()
    except Exception:
        pass


def call_api(prompt: str, options: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_eval_person_exists()
    vars_dict = context.get("vars", {})
    language = vars_dict.get("language", "ar")
    user_query = vars_dict.get("user_query")
    template_text = vars_dict.get("template")

    if user_query:
        # Evaluate user intent query
        intent_res = intent_classifier.classify_intent(user_query, language=language)
        if intent_res["is_decision_question"]:
            output_text = intent_res["handoff_message"]
        else:
            output = pipeline.generate_explanation(
                template_key="CARRIER_AR_SUMMARY",
                slots={"gene": "HBB", "condition_name": "Beta-thalassemia"},
                person_id="p_eval",
                language=language,
            )
            output_text = output["final_text"]
    elif template_text:
        output = pipeline.generate_explanation(
            template_key="COUPLE_SAME_GENE_NUMBERS",
            slots={"gene": "HBB", "condition_name": "Beta-thalassemia"},
            person_id="p_eval",
            language=language,
        )
        output_text = output["final_text"]
    else:
        output_text = "This is a screening result, not a diagnosis. [DRAFT - requires clinical sign-off]"

    return {"output": output_text}
