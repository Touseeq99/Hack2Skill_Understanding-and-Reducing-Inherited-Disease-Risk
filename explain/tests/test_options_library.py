import re

from explain.options_library import OPTIONS, CLOSING, options_for

BANNED = re.compile(r"\b(best|recommend|should|safest|most effective|success rate|guarantee|\d+\s?%)", re.IGNORECASE)


def test_seven_options_same_structure_and_equal_weight():
    assert len(OPTIONS) == 7
    for o in OPTIONS:
        for lang in ("en", "ar"):
            assert o["title"][lang] and o["body"][lang]
    lengths = [len(o["body"]["en"]) for o in OPTIONS]
    assert max(lengths) <= 1.6 * min(lengths)  # no option is described far more attractively / at greater length


def test_no_directive_or_ranking_or_success_claims():
    for lang in ("en", "ar"):
        for o in options_for(lang, "T0", "created"):
            text = o["title"] + " " + (o["body"] or "")
            assert not BANNED.search(text), text
            assert CLOSING[lang] in o["body"]


def test_detailed_options_released_after_counselling_for_t2_t3():
    locked = [o["id"] for o in options_for("en", "T2", "booked") if o["locked"]]
    assert set(locked) == {"prenatal", "pgt_m", "donor", "adoption"}
    assert all(o["body"] is None for o in options_for("en", "T3", "created") if o["locked"])
    assert not any(o["locked"] for o in options_for("en", "T2", "attended"))
    assert not any(o["locked"] for o in options_for("en", "T1", "created"))
    assert not any(o["locked"] for o in options_for("en", "T0", "created"))
