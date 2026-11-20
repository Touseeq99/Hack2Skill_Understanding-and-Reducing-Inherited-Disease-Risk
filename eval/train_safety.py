"""Train the embedding-based safety classifier and write models/safety_clf.json.

Usage:  python -m eval.train_safety

Only eval/safety_train.py and eval/safety_messages.py are used. The frozen held-out set
(eval/safety_heldout.py) is NEVER read here: hyper-parameters and thresholds come from cross-validation
on the training data alone, so the held-out score stays an honest estimate.

Thresholds are chosen for recall (PDF section 4: false negatives cost trust): for each intent the threshold is
the lowest-probability quantile of the out-of-fold positive scores that still keeps recall at the target,
capped at 0.5 so the model is never made stricter than a coin flip.
"""

import datetime
import json

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold

from backend.ml_classifier import ARTIFACT, INTENTS, MODEL_NAME, embed
from eval.safety_messages import MESSAGES
from eval.safety_train import TRAIN

RECALL_TARGET = {"distress": 0.97, "coercion": 0.97, "decision_question": 0.95, "reproductive_options": 0.93, "help_request": 0.93}
C_GRID = [0.3, 1.0, 3.0, 10.0]
SEED = 7


def _dataset():
    rows = [(t, set(e)) for t, e in TRAIN] + [(t, set(e)) for t, e in MESSAGES]
    seen, out = set(), []
    for t, e in rows:  # de-duplicate by text
        if t not in seen:
            seen.add(t)
            out.append((t, e))
    return out


_PREFIXES = ("Hi, ", "Hello, ", "Excuse me, ", "السلام عليكم، ", "مرحبا، ", "لو سمحت، ")


def _group_key(text):
    """Polite-prefix variants of a message must share a fold, otherwise CV leaks and looks too good."""
    for p in _PREFIXES:
        if text.startswith(p):
            text = text[len(p):]
    return text[:1].lower() + text[1:]


def _oof_probs(X, y, C, groups):
    skf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    oof = np.zeros(len(y))
    for tr, te in skf.split(X, y, groups):
        m = LogisticRegression(C=C, class_weight="balanced", max_iter=2000)
        m.fit(X[tr], y[tr])
        oof[te] = m.predict_proba(X[te])[:, 1]
    return oof


def _score(y, p):
    from sklearn.metrics import average_precision_score
    return average_precision_score(y, p)


def main():
    data = _dataset()
    texts = [t for t, _ in data]
    X = embed(texts)
    keys = [_group_key(t) for t in texts]
    groups = np.array([sorted(set(keys)).index(k) for k in keys])
    print(f"{len(texts)} training messages embedded ({X.shape[1]} dims) with {MODEL_NAME}")
    artifact = {"model": MODEL_NAME, "trained_at": datetime.date.today().isoformat(), "n_train": len(texts), "intents": {}}
    for intent in INTENTS:
        y = np.array([1 if intent in e else 0 for _, e in data])
        best_c = max(C_GRID, key=lambda c: _score(y, _oof_probs(X, y, c, groups)))
        oof = _oof_probs(X, y, best_c, groups)
        pos = np.sort(oof[y == 1])
        k = int(np.floor((1 - RECALL_TARGET[intent]) * len(pos)))
        threshold = float(min(0.5, pos[k] - 1e-6))
        threshold = max(threshold, 0.05)
        recall = float((oof[y == 1] >= threshold).mean())
        fpr = float((oof[y == 0] >= threshold).mean())
        model = LogisticRegression(C=best_c, class_weight="balanced", max_iter=2000).fit(X, y)
        artifact["intents"][intent] = {
            "coef": [round(float(v), 6) for v in model.coef_[0]],
            "bias": round(float(model.intercept_[0]), 6),
            "threshold": round(threshold, 4),
            "C": best_c,
            "n_pos": int(y.sum()),
            "cv_recall": round(recall, 3),
            "cv_false_positive_rate": round(fpr, 3),
        }
        print(f"{intent:22s} n_pos={int(y.sum()):3d} C={best_c:<4} threshold={threshold:.3f} CV recall={recall:.2f} CV FPR={fpr:.2f}")
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(artifact), encoding="utf-8")
    print("wrote", ARTIFACT)


if __name__ == "__main__":
    main()
