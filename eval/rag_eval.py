"""Tune and score FAQ retrieval.

  python -m eval.rag_eval tune      choose thresholds on eval/faq_dev.py only, write models/rag_config.json
  python -m eval.rag_eval report    score the frozen eval/faq_heldout.py with 95% Wilson intervals

Tuning objective: a wrong answer (the wrong block, or any answer to an out-of-scope question) costs 3, a correct
answer earns 1, abstaining costs 0. Abstaining is always safe because the caller falls back to the human handoff.
"""

import json
import sys

import numpy as np

from backend import rag
from eval.faq_dev import DEV_FAQ
from eval.faq_heldout import HELDOUT_FAQ
from eval.safety_report import wilson
from explain.faq_library import FAQ

IDS = [f["id"] for f in FAQ]


def _decide(sc, min_score, min_margin):
    order = np.argsort(sc)[::-1]
    best, second = sc[order[0]], sc[order[1]]
    if best < min_score or best - second < min_margin:
        return None
    return IDS[int(order[0])]


def _scores(items):
    return [rag.scores(q) for q, _ in items]


def tune():
    items = DEV_FAQ
    sc = _scores(items)
    best = None
    for ms in np.arange(0.40, 0.91, 0.02):
        for mg in (0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.12):
            correct = wrong = 0
            for s, (_, exp) in zip(sc, items):
                d = _decide(s, ms, mg)
                if d is None:
                    continue
                if d == exp:
                    correct += 1
                else:
                    wrong += 1
            value = correct - 3 * wrong
            key = (value, -ms)  # on ties prefer the stricter (higher) threshold
            if best is None or key > best[0]:
                best = (key, float(ms), mg, correct, wrong)
    _, ms, mg, correct, wrong = best
    cfg = {"min_score": round(ms, 3), "min_margin": mg, "tuned_on": "eval/faq_dev.py", "dev_correct": correct, "dev_wrong": wrong, "dev_n": len(items)}
    rag.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rag.CONFIG_PATH.write_text(json.dumps(cfg), encoding="utf-8")
    print("chosen:", cfg)


def report():
    cfg = rag._config()
    print("thresholds:", cfg)
    inscope = [(q, e) for q, e in HELDOUT_FAQ if e]
    oos = [(q, e) for q, e in HELDOUT_FAQ if not e]

    def fmt(k, n):
        lo, hi = wilson(k, n)
        return f"{k}/{n} = {100 * k / n:.0f}% (95% CI {100 * lo:.0f}-{100 * hi:.0f}%)"

    correct = wrong = abstain = 0
    wrong_items = []
    for q, exp in inscope:
        d = _decide(rag.scores(q), cfg["min_score"], cfg["min_margin"])
        if d is None:
            abstain += 1
        elif d == exp:
            correct += 1
        else:
            wrong += 1
            wrong_items.append((q, d, exp))
    answered_oos = [(q, _decide(rag.scores(q), cfg["min_score"], cfg["min_margin"])) for q, _ in oos]
    leaked = [x for x in answered_oos if x[1] is not None]
    print(f"in-scope ({len(inscope)}): answered correctly {fmt(correct, len(inscope))}; wrong block {wrong}; abstained (human handoff) {abstain}")
    print(f"out-of-scope ({len(oos)}): wrongly answered {fmt(len(leaked), len(oos))}")
    if "--verbose" in sys.argv:
        for w in wrong_items:
            print("  WRONG", w)
        for l in leaked:
            print("  LEAK", l)


if __name__ == "__main__":
    {"tune": tune, "report": report}[sys.argv[1] if len(sys.argv) > 1 else "report"]()
