"""Multilingual Intent Classifier for user queries in Arabic and English.

Tuned for high recall to ensure patient safety and ethical non-directiveness:
- 'decision_question' -> produces fixed non-directive handoff and triggers T2 triage.
- 'distress' or 'coercion' -> triggers immediate T3 escalation and safety resources.
"""

import re
from typing import Dict, Any, List
from explain.templates.catalog import TEMPLATES


INTENT_PATTERNS = {
    "decision_question": {
        "en": [
            r"\bshould we (?:still )?(?:get )?marr(?:y|ied)\b",
            r"\bcan we (?:still )?(?:get )?marr(?:y|ied)\b",
            r"\bis it safe to marr(?:y|ied)\b",
            r"\bwhat should we do\b",
            r"\bshould i cancel (?:the )?(?:wedding|marriage)\b",
            r"\bcan we still have children\b",
            r"\bwhat do you recommend we do\b",
        ],
        "ar": [
            r"هل نتزوج",
            r"هل نستمر بالزواج",
            r"هل نلغي الزواج",
            r"ماذا تنصحنا",
            r"ماذا يجب أن نفعل",
            r"هل آمن نتزوج",
            r"شو نسوي",
            r"هل ننفصل",
            r"هل تنصح بعدم الزواج",
        ]
    },
    "reproductive_options": {
        "en": [
            r"\bivf\b", r"\bpgt[- ]?m\b", r"\bprenatal\b",
            r"\badoption\b", r"\bdonor\b", r"\bamniocentesis\b"
        ],
        "ar": [
            r"أطفال أنابيب", r"فحص الأجنة", r"فحص ما قبل الغرس",
            r"فحص أثناء الحمل", r"سحب عينة المشيمة", r"عينة السائل الأمنيوسي"
        ]
    },
    "distress": {
        "en": [
            r"\bkill myself\b", r"\bwant to die\b", r"\bend my life\b",
            r"\bhopeless\b", r"\bself[- ]?harm\b", r"\bcan'?t go on\b"
        ],
        "ar": [
            r"انتحار", r"أريد أن أموت", r"أنهي حياتي",
            r"أؤذي نفسي", r"تعبت من الدنيا", r"لا أريد العيش"
        ]
    },
    "coercion": {
        "en": [
            r"\bforcing me\b", r"\bforced to marry\b", r"\bthreatened me\b",
            r"\bafraid of him\b", r"\bhe hurts me\b", r"\bcoerced\b"
        ],
        "ar": [
            r"مجبورة", r"مغصوبة على الزواج", r"يهددني",
            r"أهلي يجبروني", r"خائفة منه", r"ضغط عائلي إجباري"
        ]
    },
    "help_request": {
        "en": [
            r"\bhelp me\b", r"\btalk to a human\b", r"\bspeak to doctor\b",
            r"\bcall me\b", r"\bhuman please\b"
        ],
        "ar": [
            r"أحتاج مساعدة", r"تحدث مع شخص", r"أريد دكتور",
            r"اتصلوا بي", r"تواصلوا معي"
        ]
    }
}


class IntentClassifier:
    """Classifies user messages to detect triage triggers."""

    def classify_intent(self, text: str, language: str = "ar") -> Dict[str, Any]:
        """Detect intent and return matching flags, target tier, and non-directive message if applicable."""
        detected_intents: List[str] = []
        lower_text = text.lower()

        for intent, lang_map in INTENT_PATTERNS.items():
            patterns = lang_map.get("en", []) + lang_map.get("ar", [])
            for pattern in patterns:
                if re.search(pattern, lower_text, re.IGNORECASE):
                    detected_intents.append(intent)
                    break

        # Map highest triggered tier
        target_tier = "T0"
        handoff_message = None

        if "distress" in detected_intents or "coercion" in detected_intents:
            target_tier = "T3"
        elif "decision_question" in detected_intents or "reproductive_options" in detected_intents:
            target_tier = "T2"
        elif "help_request" in detected_intents:
            target_tier = "T1"

        # If user asked a decision question ("Should we get married?"):
        # The bot NEVER answers "what to do". It returns the fixed clinical handoff!
        if "decision_question" in detected_intents:
            lang_key = language if language in ("ar", "en") else "ar"
            handoff_message = TEMPLATES["DIRECTIVE_QUESTION_HANDOFF"][lang_key]["standard"]

        return {
            "query": text,
            "detected_intents": detected_intents,
            "target_tier": target_tier,
            "is_decision_question": "decision_question" in detected_intents,
            "is_distress": "distress" in detected_intents,
            "is_coercion": "coercion" in detected_intents,
            "handoff_message": handoff_message,
        }


intent_classifier = IntentClassifier()
