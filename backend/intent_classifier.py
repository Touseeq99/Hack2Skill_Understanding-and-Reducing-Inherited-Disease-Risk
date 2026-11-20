"""Multilingual Intent Classifier for user queries in Arabic and English.

Tuned for HIGH RECALL (PDF section 4: false positives cost a counsellor minute, false negatives cost
trust). Signals can only RAISE a tier; they never lower one.
- 'decision_question' -> fixed non-directive handoff and T2 triage.
- 'distress' or 'coercion' -> immediate T3 escalation and safety resources.

Arabic text is normalised (diacritics, tatweel, alef/ya/ta-marbuta variants) before matching, so spelling
variants and Gulf-dialect forms match the same patterns. Patterns are written in natural orthography and
normalised with the same function at import time.

DRAFT - requires native-speaker and clinical review; extend eval/safety_messages.py with pilot phrases.
"""

import os
import re
from typing import Dict, Any, List, Optional
from explain.templates.catalog import TEMPLATES

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه", "ک": "ك", "ی": "ي"})


def normalize(text: str) -> str:
    """Lower-case Latin text, strip Arabic diacritics/tatweel and unify letter variants."""
    return _DIACRITICS.sub("", text.lower()).translate(_AR_MAP)


_RAW_PATTERNS = {
    "decision_question": {
        "en": [
            r"\bshould (?:we|i)\b.{0,40}\b(?:still |even )?(?:get )?(?:marry|married|cancel|break up|separate|go ahead|call off|have (?:a |any )?(?:child|children|kids|baby|babies))",
            r"\bcan (?:we|i) (?:still )?(?:get )?(?:marry|married|have (?:a |any )?(?:healthy )?(?:child|children|kids|baby|babies))",
            r"\bis it (?:safe|okay|ok|wise|right|haram|allowed|a good idea)\b.{0,30}\b(?:marr|have|go ahead|child|children|baby|wedding)",
            r"\bwhat should (?:we|i) do\b", r"\bwhat would you do\b", r"\bwhat do you recommend\b",
            r"\bdo you (?:think|recommend|advise)\b.{0,30}\b(?:we|i) should\b",
            r"\bwould you (?:advise|recommend|suggest)\b",
            r"\bcancel (?:the )?(?:wedding|marriage|engagement)\b", r"\bbreak up\b", r"\bcall off\b",
            r"\bsupposed to (?:go through|marry|get married|cancel|continue|proceed)", r"\bgo(?:ing)? through with\b", r"\bproceed with\b",
            r"\badvise (?:us|me)? ?to\b", r"\bshould (?:we|i) (?:go|continue|proceed|stay|leave|stop|wait)\b", r"\bin our (?:place|shoes)\b",
        ],
        "ar": [
            r"هل (?:نتزوج|ننفصل|نلغي|نكمل|نستمر|ننجب|يجوز|ينفع|يصح|يحق|اتزوج|الغي|يجب|علينا|لازم|ممكن نتزوج)",
            r"نكمل (?:ال)?(?:زواج|خطوبه)", r"نلغي (?:ال)?(?:خطوبه|زواج|عقد)", r"(?:ال)?(?:نتزوج|نتزوجه) (?:ولا|او) لا",
            r"تنصح(?:نا|ني)", r"ماذا تنصح", r"(?:شنو|شو|وش|ايش) (?:نسوي|اسوي)", r"ماذا (?:نفعل|افعل) الان",
            r"ماذا يجب ان نفعل", r"ينفع (?:نتزوج|ننجب)", r"يصير (?:نتزوج|ننجب)",
            r"هل ا?من (?:ان )?نتزوج", r"هل ننجب", r"هل تنصح",
            r"هل (?:اكمل|الغي|اتراجع|اترك|استمر|نواصل|نتراجع)", r"لو كنت (?:مكاننا|مكاني)", r"(?:شنو|شو|وش|ايش) (?:بتسوي|تسوي|تنصح|ترى|تشوف)",
            r"نكمل ولا", r"نتراجع", r"نواصل (?:ال)?(?:زواج|خطوبه)",
        ],
    },
    "reproductive_options": {
        "en": [r"\bivf\b", r"\bpgt[- ]?m?\b", r"\bprenatal\b", r"\badoption\b", r"\bdonor\b", r"\bamniocentesis\b",
               r"\bembryos?\b", r"\bcvs\b", r"\bsurrogacy\b", r"\bpregnan(?:t|cy) test"],
        # extra stems
        "en_extra": [r"preimplantation", r"\bsperm\b", r"\bsurrog", r"(?:healthy|unaffected) (?:baby|child)", r"fertility treatment", r"\bicsi\b", r"test(?:ing)? (?:the )?baby"],
        "ar": [r"اطفال (?:ال)?انابيب", r"فحص (?:ال)?(?:اجنه|جنين)", r"فحص ما قبل الغرس", r"اجنه", r"(?:فحص|اختبار).{0,15}الحمل",
               r"عينه المشيمه", r"السائل الامنيوسي", r"متبرع", r"تبرع (?:ب)?(?:ال)?(?:بويضات|حيوانات)", r"كفاله", r"تبني", r"فحص (?:ال)?جنين"],
        "ar_extra": [r"تلقيح", r"طفل سليم", r"انجاب (?:طفل )?سليم", r"زراعه", r"حقن مجهري", r"علاج (?:ال)?عقم"],
    },
    "distress": {
        "en": [
            r"\bkill myself\b", r"\bwant to die\b", r"\bwish i (?:was|were) dead\b", r"\bend(?:ing)? (?:my life|it all)\b",
            r"\bhopeless\b", r"\bself[- ]?harm\b", r"\bcan'?t go on\b", r"\b(?:don'?t|do not) want to (?:live|be alive|exist)\b",
            r"\bno point in (?:going on|living|life|continuing)\b", r"\b(?:hurt|harm|cut) myself\b", r"\bsuicid",
            r"\bbetter off (?:dead|without me)\b", r"\bgive up on life\b", r"\bnothing to live for\b",
            r"\bdisappear\b", r"\bcan'?t (?:take|do|handle|cope with) this (?:anymore|any more)\b", r"\bcan'?t (?:carry on|continue)\b",
        ],
        "ar": [
            r"انتحار", r"انتحر", r"(?:اريد|ابي|ابغي|ودي|اتمني|نفسي) (?:ان )?اموت", r"(?:ما|لا) (?:ابي|ابغي|اريد|اتحمل) (?:ان )?(?:اعيش|العيش|الحياه)",
            r"(?:انهي|انهاء|انهيت) حياتي", r"تعبت من (?:ال)?(?:حياه|دنيا)", r"(?:اوذي|اؤذي|اذي|اجرح) نفسي", r"لا فائده من (?:ال)?(?:استمرار|حياه|عيش)",
            r"كرهت حياتي", r"ما في امل", r"يئست",
            r"(?:لا|ما) (?:اريد|ابي|ابغي|اقدر) (?:ان )?(?:استمر|اكمل|اتحمل)", r"حاس[هي]? (?:اني|اني) ما اقدر", r"ما اقدر (?:اكمل|استمر|اتحمل)", r"اختفي",
        ],
    },
    "coercion": {
        "en": [
            r"\bforc(?:ing|ed|es) (?:me|us)\b", r"\bforced to (?:marry|get married)\b", r"\bthreat(?:en|ens|ened|ening) (?:me|us)\b",
            r"\b(?:afraid|scared|terrified) of (?:him|her|them|my (?:father|brother|husband|family|uncle)|what)\b",
            r"\b(?:hits?|beats?|hurts?|slaps?) me\b", r"\bhe hurts me\b", r"\bcoerc", r"\bno choice\b", r"\bdecided for me\b",
            r"\bpunish(?:ed)? me\b", r"\bpressur(?:e|ed|ing) me (?:into|to)\b", r"\bmade me (?:sign|agree|marry)\b",
            r"against my will", r"\bmade to (?:marry|sign|agree)\b", r"\bcontrols? me\b", r"\b(?:scares?|frightens?|intimidates?) me\b", r"\b(?:have|has|had) to marry\b",
        ],
        "ar": [
            r"مجبر(?:ه|ين|ينني|ون)?", r"(?:اجبر|يجبر|تجبر)(?:وني|ني|ونني|وها|وا)", r"اجبرت", r"مغصوب", r"يهدد(?:ني|وني|نا)?", r"هدد(?:ني|وني)",
            r"(?:خايف|خائف|خايفه|خائفه) (?:منه|منها|منهم|من (?:ابي|اخي|زوجي|اهلي|عمي))", r"اخاف (?:منه|منها|منهم|من (?:ابي|اخي|زوجي|اهلي|عمي))",
            r"(?:يضرب|ضرب|تضرب)(?:ني|وني)", r"(?:ما|لا) (?:عندي|لدي|عندنا) خيار", r"قرر(?:وا|ت)? عني", r"يعاقب(?:ني|وني)", r"ضغط (?:اسري|عائلي|من اهلي)",
            r"لازم (?:اتزوج|اوافق|اقبل)", r"(?:وا?لا|والا) (?:يطرد|يضرب|يقتل|يحرم)", r"يتحكم (?:في|ب)ي", r"يخوف(?:ني|وني)", r"ضد رغبتي", r"بدون موافقتي", r"رغما عني",
        ],
    },
    "help_request": {
        "en": [
            r"\bhelp me\b", r"\btalk to (?:a |an )?(?:human|person|someone|counsel+or|doctor|specialist)\b",
            r"\bspeak (?:to|with) (?:a |an |the )?(?:human|person|someone|counsel+or|doctor|specialist)\b",
            r"\bcall me\b", r"\bhuman please\b", r"\bneed (?:a |to see a )?doctor\b",
            r"\b(?:can )?someone (?:please )?explain\b", r"\bexplain (?:this|my|the) result\b",
            r"\bring me\b", r"\bcall (?:me )?back\b", r"\bcontact me\b", r"\bsomeone (?:to )?(?:contact|call|reach)\b",
        ],
        "ar": [
            r"احتاج مساعده", r"(?:اتكلم|اتحدث|اكلم|اتواصل) مع (?:دكتور|مرشد|شخص|احد|مختص|طبيب)", r"(?:اريد|ابي|ابغي) (?:دكتور|مرشد|طبيب|مختص)",
            r"اتصلوا(?: بي)?", r"تواصلوا(?: معي)?", r"ساعدوني", r"ساعدني", r"اشرح(?:وا)? لي (?:ال)?نتيجه",
            r"يتواصل (?:معي|معنا)", r"يتصل (?:بي|بنا)", r"يكلمني", r"يكلمنا",
        ],
    },
}

INTENT_PATTERNS = {
    intent: {lang: [re.compile(normalize(p), re.IGNORECASE) for p in pats] for lang, pats in lang_map.items()}
    for intent, lang_map in _RAW_PATTERNS.items()
}


class IntentClassifier:
    """Classifies user messages to detect triage triggers (keyword rules OR embedding model)."""

    @staticmethod
    def rule_intents(text: str) -> List[str]:
        """Keyword/regex lexicon only (matched against BOTH languages: people mix scripts)."""
        norm_text = normalize(text)
        return [intent for intent, lang_map in INTENT_PATTERNS.items()
                if any(p.search(norm_text) for pats in lang_map.values() for p in pats)]

    @staticmethod
    def ml_result(text: str) -> Optional[Dict[str, Any]]:
        """Embedding-model verdict, or None when disabled (SAFETY_ML=0) or unavailable (fail-safe: rules only)."""
        if os.environ.get("SAFETY_ML", "1") == "0":
            return None
        try:
            from backend import ml_classifier
            return ml_classifier.detect(text)
        except Exception:
            return None

    def classify_intent(self, text: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Detect intent and return matching flags, target tier, and non-directive message if applicable."""
        # Auto-detect language if not explicitly provided
        if not language or language not in ("ar", "en"):
            has_arabic = bool(re.search(r"[\u0600-\u06FF]", text))
            language = "ar" if has_arabic else "en"

        by_rules = self.rule_intents(text)
        ml = self.ml_result(text)
        by_ml = ml["intents"] if ml else []
        # Union: a signal from either source counts (signals only ever raise a tier).
        detected_intents = list(dict.fromkeys(by_rules + by_ml))

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
            "detected_by": {"rules": by_rules, "model": by_ml, "model_available": ml is not None},
            "target_tier": target_tier,
            "is_decision_question": "decision_question" in detected_intents,
            "is_distress": "distress" in detected_intents,
            "is_coercion": "coercion" in detected_intents,
            "handoff_message": handoff_message,
        }


intent_classifier = IntentClassifier()
