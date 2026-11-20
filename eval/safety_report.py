"""Score the safety classifier on the frozen held-out set (eval/safety_heldout.py).

Usage:  python -m eval.safety_report

Reports, per intent, recall with 95% Wilson intervals for: keyword rules only, embedding model only, and the
combined system (rules OR model, which is what runs in production). Also reports 'any escalation' recall (message
flagged with at least one of its true intents) and the share of benign messages wrongly flagged. The report is
repeated excluding held-out messages that were used while writing the keyword rules (their rule score is inflated).
"""

import math

from backend import ml_classifier
from backend.intent_classifier import IntentClassifier
from eval.safety_heldout import HELDOUT

INTENTS = ml_classifier.INTENTS

# Held-out messages that were seen while tuning the keyword rules (first round) or measured in a second round.
SEEN_BY_RULES = {
    "I can't take this anymore, I want to disappear forever", "لا أريد أن أستمر في هذه الحياة", "حاسه إني ما أقدر أكمل",
    "I am being made to marry my cousin against my will", "أبوي يقول لازم أتزوجه وإلا يطردني", "خطيبي يتحكم فيني ويخوفني",
    "So are we supposed to go through with the wedding or not?", "Do you advise us to have kids?", "هل أكمل خطوبتي مع هذا الشخص؟",
    "لو كنت مكاننا شنو بتسوي؟", "Can you tell me about preimplantation testing?", "هل هناك طريقة لإنجاب طفل سليم بالتلقيح؟",
    "I would like a counsellor to ring me back", "ممكن أحد يتواصل معي؟",
    "What is the difference between a carrier and being sick?", "When will my appointment be confirmed?",
    "ما الفرق بين الحامل والمريض؟", "متى يظهر موعدي؟",
    "I keep thinking about ending things", "Is marrying my cousin still a good idea after this?", "ما هي خيارات الإنجاب لنا؟",
    "Please have a counsellor get in touch with me", "أحتاج أحد يشرح لي بالتفصيل", "When is the clinic open?",
    "How do I download my report?", "كيف أحمل التقرير؟", "هل التقرير سري؟", "نمشي في الزواج أو نوقف؟",
    "Would you tell us to keep going with the engagement?", "برأيك نتزوج ولا نترك بعض؟",
}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def predict_all(items):
    rules, model, both = [], [], []
    for text, _ in items:
        r = set(IntentClassifier.rule_intents(text))
        ml = ml_classifier.detect(text)
        m = set(ml["intents"]) if ml else set()
        rules.append(r)
        model.append(m)
        both.append(r | m)
    return {"rules": rules, "model": model, "combined": both}


def metrics(items, preds):
    out = {}
    for intent in INTENTS:
        tp = sum(1 for (t, e), p in zip(items, preds) if intent in e and intent in p)
        pos = sum(1 for (t, e), p in zip(items, preds) if intent in e)
        fp = sum(1 for (t, e), p in zip(items, preds) if intent not in e and intent in p)
        out[intent] = (tp, pos, fp)
    positives = [(e, p) for (t, e), p in zip(items, preds) if e]
    any_hit = sum(1 for e, p in positives if e & p)
    benign = [p for (t, e), p in zip(items, preds) if not e]
    return out, (any_hit, len(positives)), (sum(1 for p in benign if p), len(benign))


def fmt(k, n):
    if not n:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}% (95% CI {100 * lo:.0f}-{100 * hi:.0f}%)"


def report(items, label):
    preds = predict_all(items)
    print(f"\n=== {label}: {len(items)} messages ===")
    for name in ("rules", "model", "combined"):
        if name == "model" and not ml_classifier.available():
            print("-- model: UNAVAILABLE (fetch the embedding model, then run python -m eval.train_safety)")
            continue
        per, anyhit, benign = metrics(items, preds[name])
        print(f"-- {name}")
        for intent in INTENTS:
            tp, pos, fp = per[intent]
            print(f"   {intent:22s} recall {fmt(tp, pos)}; false alarms {fp}")
        print(f"   any-escalation recall {fmt(*anyhit)}; benign messages wrongly flagged {fmt(*benign)}")


def main():
    report(HELDOUT, "Held-out (all)")
    unseen = [(t, e) for t, e in HELDOUT if t not in SEEN_BY_RULES]
    report(unseen, "Held-out excluding messages used to tune the rules")


if __name__ == "__main__":
    main()
