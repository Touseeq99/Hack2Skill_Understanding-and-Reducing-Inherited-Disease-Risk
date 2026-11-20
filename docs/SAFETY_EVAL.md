# Safety classifier evaluation (honest numbers)

The chat assistant never answers "what should we do". A classifier decides when a person is routed to a human
(T2 decision question, T3 distress or coercion). This page records how well it works and how the numbers were obtained.

## The system

| Layer | What it is | Where |
|---|---|---|
| Keyword rules | Regex lexicon, Arabic text normalised, EN + MSA + Gulf | `backend/intent_classifier.py` |
| Embedding model | `paraphrase-multilingual-MiniLM-L12-v2` (fastembed / ONNX, about 220 MB, runs offline) + one logistic regression per intent, thresholds chosen for recall | `backend/ml_classifier.py`, weights in `models/safety_clf.json` |
| Combination | A message is flagged if the rules OR the model flag it. Signals only raise a tier. Rules that fired on the model alone carry a `~ML` suffix (for example `TRI-T3-003~ML`) so counsellors and auditors can see it | `backend/triage_router.py` |
| Fail-safe | If the model or weights are missing, rules still run, and every chat reply offers a human | `human_offer: true` |

## Result on the frozen held-out set (`eval/safety_heldout.py`, 103 messages: 73 with at least one risk intent, 30 benign)

Reproduce with `python -m eval.safety_report`. Recall = share of messages with that intent that were flagged.

| Intent | Rules only | Combined (production) |
|---|---|---|
| distress (17) | 4/17 = 24% | **17/17 = 100%** (95% CI 82-100%) |
| coercion (18) | 10/18 = 56% | **18/18 = 100%** (95% CI 82-100%) |
| decision question (19) | 9/19 = 47% | **18/19 = 95%** (95% CI 75-99%) |
| reproductive options (12) | 8/12 = 67% | **12/12 = 100%** (95% CI 76-100%) |
| help request (12) | 2/12 = 17% | **12/12 = 100%** (95% CI 76-100%) |
| **any escalation** (73) | 30/73 = 41% (CI 31-53%) | **72/73 = 99%** (CI 93-100%) |
| benign messages wrongly flagged (30) | 0/30 | **7/30 = 23%** (CI 12-41%) |

Excluding the 18 held-out messages that were seen while tuning the rules, the combined system scores 59/60 = 98%
any-escalation recall (CI 91-100%) and flags 7/25 = 28% of benign messages.

The price of high recall is **false alarms**: about one benign message in four (and, per intent, 5 to 9 messages that
carried a different intent) was flagged. That matches the PDF's stance (a false positive costs a counsellor minute, a
false negative costs trust), but it will add noise to the queue and can show the crisis panel to someone who only
asked for a call-back. A known example: "thanks for the help" in Arabic scores as a help request.

## How the numbers were obtained, and why they are still optimistic

- `eval/safety_heldout.py` was written **before** the training data and the model existed and is never used for
  training or threshold selection. Hyper-parameters and thresholds come from 5-fold cross-validation on
  `eval/safety_train.py` + `eval/safety_messages.py` only (grouped so that polite-prefix copies of a message stay in one fold).
- The held-out set was nevertheless **scored three times**: once with the first model, once after a methodology fix
  (grouped cross-validation, which removed leakage that had made the thresholds too strict), and once after adding
  benign "thanks / greeting" messages to the training set because a test of mine failed. No changes were made by
  reading which held-out messages failed, but repeated scoring still leaks a little information.
- The first scoring (before the grouped-CV fix) gave 95% any-escalation recall and 88% distress recall.
- The same people wrote the training data, the held-out data and the rules. Real users will phrase things differently.
- The held-out set has only 73 positives; a 95% interval of 93-100% for the overall figure and 82-100% per intent is
  wide. "100% recall" must not be quoted without the interval.
- Nobody outside the team has reviewed the Arabic. The Gulf-dialect coverage in particular is thin.
- Rules measured earlier: about 12% on two small fresh sets, which is why the keyword lexicon alone is not trusted.

## What is NOT claimed

- No claim of clinical validity or regulatory readiness. The classifier is an escalation aid; a human is always one tap away.
- No claim that the recall will hold on real, dialect-rich, code-switched messages.

## Before any real use

1. Have native Arabic speakers (Gulf plus expat languages) write and review a new held-out set, label it blind, and
   score the frozen model once. Set a release threshold first (for example lower CI bound of recall >= 90% on distress
   and coercion) and decide how many false alarms the counselling team can absorb.
2. Add de-identified pilot messages to the training data and retrain (`python -m eval.train_safety`).
3. Consider a second, higher-confidence tier for model-only coercion so that low-confidence hits go to T2 review without
   the crisis panel; this is a clinical-policy decision for the clinical partner.
4. Have the clinical partner verify the crisis numbers in `backend/safety.py` (`verify_before_use`).

## Running it

```bash
pip install -r requirements-ml.txt          # fastembed, scikit-learn, numpy
python -m eval.train_safety                 # first run downloads the model (about 220 MB) into models/fastembed
python -m eval.safety_report                # scores the frozen held-out set
```

Set `SAFETY_ML=0` to run on rules only (tests do this by default). `/health` reports whether the embedding model is loaded.

## Privacy note

Chat text is stored in `chat_message` (shown to the assigned counsellor, erased on a deletion request). The append-only
audit log records only the event and the intent labels, never the message text. The embedding model runs locally; no
message text leaves the server. Audit rows written before this change may still contain a short prefix of old queries.
