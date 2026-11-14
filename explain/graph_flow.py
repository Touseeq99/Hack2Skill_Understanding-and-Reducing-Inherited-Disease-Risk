"""State graph flow: Explain -> Teach-back Quiz -> Route.

Follows LangGraph architecture:
1. 'explain' node: generates validated, clinician-approved explanation in chosen language.
2. 'quiz' node: presents 3-5 item teach-back questions.
   - If user fails twice -> router escalates to counsellor booking.
3. 'route' node: evaluates deterministic router rules and assigns tier.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from explain.pipeline import ExplanationPipeline
from backend.database import db, Database


QUIZ_QUESTIONS = {
    "en": [
        {
            "id": "q1_carrier_meaning",
            "question": "What does being a genetic carrier mean for your own personal health?",
            "options": [
                {"id": "a", "text": "You have an active disease and need treatment.", "correct": False},
                {"id": "b", "text": "You are typically healthy, but it matters if your partner carries the same gene.", "correct": True},
                {"id": "c", "text": "You can never have children.", "correct": False},
            ],
            "explanation": "Carriers have one working gene copy and are usually completely healthy. Risk to children arises if both parents carry changes in the same gene."
        },
        {
            "id": "q2_risk_vs_diagnosis",
            "question": "Is this carrier screening result a clinical diagnosis?",
            "options": [
                {"id": "a", "text": "No, this is an educational screening result, not a clinical diagnosis.", "correct": True},
                {"id": "b", "text": "Yes, it guarantees a medical condition.", "correct": False},
            ],
            "explanation": "Carrier screening measures statistical inheritance risks; it is not a medical diagnosis."
        },
        {
            "id": "q3_same_gene_probability",
            "question": "If two partners both carry a change in the SAME recessive gene, what is the chance in EACH pregnancy of having an affected child?",
            "options": [
                {"id": "a", "text": "1 in 4 (25%)", "correct": True},
                {"id": "b", "text": "1 in 2 (50%)", "correct": False},
                {"id": "c", "text": "100%", "correct": False},
            ],
            "explanation": "For autosomal recessive conditions where both partners are carriers, the chance is 1 in 4 (25%) in each pregnancy."
        },
        {
            "id": "q4_residual_risk",
            "question": "Does a negative screening result mean zero possibility of any inherited condition?",
            "options": [
                {"id": "a", "text": "Yes, zero risk forever.", "correct": False},
                {"id": "b", "text": "No, standard screening greatly reduces risk, but a small residual risk always remains.", "correct": True},
            ],
            "explanation": "No genetic panel tests every possible variant; small residual risk always remains."
        },
    ],
    "ar": [
        {
            "id": "q1_carrier_meaning",
            "question": "ماذا تعني صفة 'حامل للجين' بالنسبة لصحتك الشخصية؟",
            "options": [
                {"id": "a", "text": "أنك مريض وتحتاج لعلاج فوري.", "correct": False},
                {"id": "b", "text": "أنك تتمتع بصحة طبيعية عادة، وتكمن الأهمية إذا كان شريكك يحمل نفس الجين.", "correct": True},
                {"id": "c", "text": "أنك لن تتمكن من الإنجاب مطلقا.", "correct": False},
            ],
            "explanation": "حامل الجين يتمتع بصحة طبيعية عادة لأن لديه نسخة أخرى تعمل بشكل سليم."
        },
        {
            "id": "q2_risk_vs_diagnosis",
            "question": "هل فحص التوافق الحالي يعتبر تشخيصاً طبياً نهائياً؟",
            "options": [
                {"id": "a", "text": "لا، هذا فحص استكشافي للاحتمالات وليس تشخيصاً طبياً.", "correct": True},
                {"id": "b", "text": "نعم، هو تشخيص قاطع.", "correct": False},
            ],
            "explanation": "الفحص الاستكشافي يحدد الاحتمالات الوراثية وليس تشخيصاً للمرض."
        },
        {
            "id": "q3_same_gene_probability",
            "question": "إذا كان كلا الشريكين حاملين لتغير في نفس الجين المتنحي، فما احتمال ولادة طفل مصاب في كل حمل؟",
            "options": [
                {"id": "a", "text": "1 من كل 4 (25%)", "correct": True},
                {"id": "b", "text": "1 من كل 2 (50%)", "correct": False},
                {"id": "c", "text": "100%", "correct": False},
            ],
            "explanation": "في الوراثة المتنحية، إذا كان الأبوان حاملين لنفس الجين فإن نسبة الإصابة هي 1 من 4 في كل حمل."
        },
        {
            "id": "q4_residual_risk",
            "question": "هل تعني النتيجة السليمة انعدام الخطر تماماً بنسبة 100%؟",
            "options": [
                {"id": "a", "text": "نعم، خطر منعدم تماماً.", "correct": False},
                {"id": "b", "text": "لا، الفحص يقلل الخطر بشكل كبير ولكن تبقى احتمالية متبقية بسيطة.", "correct": True},
            ],
            "explanation": "لا يوجد فحص وراثي يشمل كل الطفرات الممكنة، لذا تبقى دائماً احتمالية متبقية بسيطة."
        },
    ]
}


class FlowState(BaseModel):
    person_id: str
    template_key: str
    slots: Dict[str, Any]
    language: str = "ar"
    reading_level: str = "standard"
    
    # State transitions
    step: str = "explain"  # "explain", "quiz", "route", "completed"
    explanation_text: Optional[str] = None
    quiz_attempts: int = 0
    quiz_score: float = 0.0
    teach_back_passed: bool = False
    teach_back_failed_twice: bool = False
    assigned_tier: str = "T0"
    fired_rule_ids: List[str] = Field(default_factory=list)
    system_action: str = "self_serve"


class ExplainQuizRouterGraph:
    """Explicit state graph executing: explain -> quiz -> route."""

    def __init__(self, database: Optional[Database] = None):
        self.db = database or db
        self.pipeline = ExplanationPipeline(database=self.db)

    def step_explain(self, state: FlowState) -> FlowState:
        """Node 1: Generate validated explanation."""
        res = self.pipeline.generate_explanation(
            template_key=state.template_key,
            slots=state.slots,
            person_id=state.person_id,
            language=state.language,
            reading_level=state.reading_level,
        )
        state.explanation_text = res["final_text"]
        state.step = "quiz"
        return state

    def step_quiz(self, state: FlowState, answers: Dict[str, str]) -> FlowState:
        """Node 2: Evaluate teach-back quiz answers.
        
        Args:
            answers: dict mapping question_id -> chosen option_id ('a', 'b', etc.)
        """
        questions = QUIZ_QUESTIONS.get(state.language, QUIZ_QUESTIONS["en"])
        correct_count = 0
        total_questions = len(questions)

        for q in questions:
            chosen = answers.get(q["id"])
            correct_opt = next((opt["id"] for opt in q["options"] if opt["correct"]), None)
            if chosen == correct_opt:
                correct_count += 1

        score = (correct_count / total_questions) * 100.0
        state.quiz_score = round(score, 1)
        state.quiz_attempts += 1

        # Record comprehension response in DB
        conn = self.db.get_connection()
        cur = conn.cursor()
        import uuid
        cur.execute("""
            INSERT INTO comprehension_response (id, person_id, quiz_id, phase, score, answers, language)
            VALUES (?, ?, ?, 'post', ?, ?, ?)
        """, (
            str(uuid.uuid4()),
            state.person_id,
            "teach_back_v1",
            state.quiz_score,
            str(answers),
            state.language,
        ))
        conn.commit()
        conn.close()

        # Check pass criteria (>= 75% correct, i.e. at least 3 of 4)
        if score >= 75.0:
            state.teach_back_passed = True
            state.step = "route"
        else:
            state.teach_back_passed = False
            if state.quiz_attempts >= 2:
                state.teach_back_failed_twice = True
                state.step = "route"
            else:
                # Give user another chance
                state.step = "quiz"

        return state

    def step_route(self, state: FlowState, base_tier: str = "T0") -> FlowState:
        """Node 3: Route based on teach-back score and risk category."""
        state.fired_rule_ids = []
        final_tier = base_tier

        # If teach-back failed twice -> router rule TRI-T1-002 fires!
        if state.teach_back_failed_twice:
            state.fired_rule_ids.append("TRI-T1-002")
            if final_tier == "T0":
                final_tier = "T1"
            state.system_action = "offer_counsellor_booking"
        elif final_tier in ("T2", "T3"):
            state.system_action = "mandatory_counsellor_booking"
        else:
            state.system_action = "self_serve_options_library"

        state.assigned_tier = final_tier
        state.step = "completed"
        return state


graph = ExplainQuizRouterGraph()
