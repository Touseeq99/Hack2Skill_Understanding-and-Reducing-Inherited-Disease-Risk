"""Strict clinical safety validator for patient-facing explanations.

Ensures:
1. Exact number preservation (no hallucinated or modified risk probabilities).
2. Required clinical disclaimers present.
3. Zero banned phrases (directive, stigmatising, deterministic, or cultural blame).
4. Reading level validation.
"""

import re
from typing import Dict, List, Any, Tuple


DIRECTIVE_PHRASES = [
    "you should not marry", "we recommend you not", "do not marry",
    "you must terminate", "you should break up", "we advise against marriage",
    "you ought to separate", "you have to cancel", "we strongly advise against this union",
    "لا يجب أن تتزوجا", "ننصح بعدم الزواج", "عليك إنهاء العلاقة",
    "يجب إلغاء الزواج", "لا تتزوج", "ننصحكم بعدم الإنجاب", "عليك الانفصال",
]

STIGMATISING_PHRASES = [
    "defective gene", "bad gene", "faulty gene", "tainted blood",
    "ruined", "flawed gene", "damaged gene", "abnormal person",
    "جين معيب", "جين تالف", "جين فاسد", "دم ملوث", "جين مشوه", "إنسان غير طبيعي",
]

DETERMINISTIC_PHRASES = [
    "your child will have", "your baby will be sick",
    "your child is guaranteed to have", "will definitely suffer",
    "طفلك سيولد مريضاً بالتأكيد", "طفلك سيكون مريضاً", "سيعاني طفلك حتماً",
]

BLAME_PHRASES = [
    "cousin marriage is dangerous", "tradition is to blame",
    "fault of your culture", "backward practice",
    "خطأ العادات والتقاليد", "زواج الأقارب جريمة", "ذنب العائلة",
]

REQUIRED_DISCLAIMERS_EN = [
    "screening result, not a diagnosis",
    "requires clinical sign-off",
]

REQUIRED_DISCLAIMERS_AR = [
    "فحص استكشافي وليس تشخيصاً طبياً",
    "requires clinical sign-off",  # tag present in brackets
]


def extract_numbers_and_frequencies(text: str) -> List[str]:
    """Extract numeric patterns including integers, fractions like '1 in 4', and decimals."""
    # Match patterns like '1 in 4', '1 من 4', standalone digits '96', '94', '2.8'
    frequencies = re.findall(r"\b\d+\s+(?:in|من)\s+\d+\b", text, re.IGNORECASE)
    # Match standalone numbers
    raw_numbers = re.findall(r"\b\d+(?:\.\d+)?\b", text)
    return sorted(frequencies + raw_numbers)


def calculate_reading_level(text: str, language: str = "en") -> float:
    """Simple reading level estimator (words per sentence and character length)."""
    sentences = [s.strip() for s in re.split(r"[.!?؟]\s+", text) if s.strip()]
    if not sentences:
        return 0.0
    words = text.split()
    avg_sentence_len = len(words) / max(len(sentences), 1)
    return round(avg_sentence_len, 2)


class ExplanationValidator:
    """Validates explanation text against strict safety and clinical accuracy rules."""

    def __init__(self):
        self.all_banned_phrases = (
            DIRECTIVE_PHRASES + STIGMATISING_PHRASES + DETERMINISTIC_PHRASES + BLAME_PHRASES
        )

    def validate(
        self,
        candidate_text: str,
        source_template: str,
        language: str = "en",
        reading_level: str = "standard",
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """Validate candidate text.
        
        Returns:
            (is_valid, list_of_errors, metadata)
        """
        errors: List[str] = []
        lower_cand = candidate_text.lower()

        # 1. Banned phrases check (Case-insensitive)
        for phrase in self.all_banned_phrases:
            if phrase.lower() in lower_cand:
                errors.append(f"Banned phrase detected: '{phrase}'")

        # 2. Required disclaimers check
        if language == "ar":
            has_screen_disclaimer = (
                "استكشافي" in candidate_text or "ليس تشخيصاً" in candidate_text or "screening" in lower_cand
            )
        else:
            has_screen_disclaimer = "screening result, not a diagnosis" in lower_cand

        if not has_screen_disclaimer:
            errors.append("Missing required screening disclaimer: 'This is a screening result, not a diagnosis'")

        if "requires clinical sign-off" not in lower_cand:
            errors.append("Missing required status disclaimer: 'DRAFT - requires clinical sign-off'")

        # 3. Numeric drift check
        source_nums = extract_numbers_and_frequencies(source_template)
        cand_nums = extract_numbers_and_frequencies(candidate_text)

        if source_nums != cand_nums:
            errors.append(
                f"Numeric drift detected! Source numbers {source_nums} do not match candidate numbers {cand_nums}."
            )

        # 4. Reading level assessment
        reading_score = calculate_reading_level(candidate_text, language)
        if reading_level == "simple" and reading_score > 35:
            errors.append(f"Reading level too complex for 'simple' mode (avg sentence length {reading_score} words > 35).")

        is_valid = len(errors) == 0
        metadata = {
            "is_valid": is_valid,
            "errors": errors,
            "reading_score": reading_score,
            "source_numbers": source_nums,
            "candidate_numbers": cand_nums,
        }

        return is_valid, errors, metadata


validator = ExplanationValidator()
