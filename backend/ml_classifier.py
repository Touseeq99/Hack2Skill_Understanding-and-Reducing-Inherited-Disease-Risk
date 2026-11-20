"""Embedding-based safety classifier (multilingual, runs offline after the first model download).

Pipeline: multilingual sentence embedding (fastembed / ONNX, no PyTorch) -> one logistic regression per intent
(weights stored in models/safety_clf.json and evaluated with numpy) -> per-intent probability thresholds chosen
for HIGH RECALL (see eval/train_safety.py). The keyword rules in backend/intent_classifier.py stay in place as a
floor: the final decision is rules OR model.

Fail-safe: if the embedding model or the weights are missing, `detect()` returns None and the caller falls back
to the rules only (the chat reply still offers a human). It never raises into the request path.
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

try:
    import numpy as np
except ImportError:  # optional ML dependency: without it the app runs on keyword rules only
    np = None

log = logging.getLogger("safety_ml")

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.environ.get("EMBED_CACHE_DIR", ROOT / "models" / "fastembed"))
ARTIFACT = Path(os.environ.get("SAFETY_CLF_PATH", ROOT / "models" / "safety_clf.json"))
INTENTS = ["distress", "coercion", "decision_question", "reproductive_options", "help_request"]

_lock = threading.Lock()
_embedder = None
_weights: Optional[Dict] = None
_load_failed = False


def _get_embedder():
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding  # imported lazily: optional dependency
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _embedder = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(CACHE_DIR))
    return _embedder


def embed(texts: List[str]) -> np.ndarray:
    vecs = np.array(list(_get_embedder().embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.maximum(norms, 1e-9)


def _load() -> Optional[Dict]:
    global _weights, _load_failed
    if _weights is not None or _load_failed:
        return _weights
    with _lock:
        if _weights is None and not _load_failed:
            try:
                data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
                if data.get("model") != MODEL_NAME:
                    raise ValueError("weights were trained for a different embedding model")
                _get_embedder()  # fail now (not on the first request) if the model cannot be loaded
                _weights = data
            except Exception as e:  # missing weights, missing model, offline first run...
                log.warning("ML safety classifier unavailable, using rules only: %s", e)
                _load_failed = True
    return _weights


def available() -> bool:
    return _load() is not None


def probabilities(text: str) -> Optional[Dict[str, float]]:
    w = _load()
    if w is None:
        return None
    try:
        x = embed([text])[0]
    except Exception as e:
        log.warning("embedding failed, using rules only: %s", e)
        return None
    out = {}
    for intent in INTENTS:
        p = w["intents"][intent]
        z = float(np.dot(np.array(p["coef"], dtype=np.float32), x) + p["bias"])
        out[intent] = float(1.0 / (1.0 + np.exp(-z)))
    return out


def detect(text: str) -> Optional[Dict[str, object]]:
    """Return {'intents': [...], 'probabilities': {...}} or None when the model is unavailable."""
    probs = probabilities(text)
    if probs is None:
        return None
    thresholds = _weights["intents"]
    return {
        "intents": [i for i in INTENTS if probs[i] >= thresholds[i]["threshold"]],
        "probabilities": {k: round(v, 3) for k, v in probs.items()},
    }


def reset_for_tests() -> None:
    global _weights, _load_failed
    _weights, _load_failed = None, False
