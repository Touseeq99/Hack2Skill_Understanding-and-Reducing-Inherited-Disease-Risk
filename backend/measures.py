"""Validated-style outcome measures (PDF section 10): decisional conflict and anxiety.

- SURE (4 yes/no items): Sure of myself, Understand the information, Risk-benefit ratio clear, Enough support.
  A total below 4 flags decisional conflict (standard SURE cut-off).
- GAD-2 (2 items scored 0-3): total >= 3 is a positive screen for anxiety.

Scores are always computed on the server from the raw item answers.
These are screening/measurement aids, not diagnoses. DRAFT - requires clinical sign-off.
"""

from typing import Dict, List

PHASES = {
    "sure": ("after_explanation", "after_counselling"),
    "anxiety": ("before_counselling", "after_counselling"),
}


def score_measure(measure: str, items: List[int]) -> Dict[str, object]:
    if measure == "sure":
        if len(items) != 4 or any(i not in (0, 1) for i in items):
            raise ValueError("SURE needs 4 items, each 0 (no) or 1 (yes).")
        total = sum(items)
        return {"score": float(total), "flag": total < 4, "flag_name": "decisional_conflict"}
    if measure == "anxiety":
        if len(items) != 2 or any(i not in (0, 1, 2, 3) for i in items):
            raise ValueError("The anxiety check needs 2 items, each scored 0 to 3.")
        total = sum(items)
        return {"score": float(total), "flag": total >= 3, "flag_name": "anxiety_screen_positive"}
    raise ValueError("Unknown measure.")
