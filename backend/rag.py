"""Retrieval over the approved FAQ library (no generation).

A question is embedded with the same multilingual model as the safety classifier and compared with the example
questions of every approved block. The best block is returned VERBATIM when the similarity and the margin over
the runner-up clear thresholds; otherwise nothing is returned and the caller falls back to the handoff message.

Answers are never composed by a language model, so numbers, disclaimers and wording stay exactly as approved.
Thresholds were chosen on eval/faq_dev.py only; eval/faq_heldout.py is the frozen test (see docs/RAG_EVAL.md).
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

from backend import ml_classifier
from explain.faq_library import FAQ, with_suffix

log = logging.getLogger("rag")
CONFIG_PATH = Path(os.environ.get("RAG_CONFIG_PATH", ml_classifier.ROOT / "models" / "rag_config.json"))
DEFAULTS = {"min_score": 0.62, "min_margin": 0.03}

_lock = threading.Lock()
_index: Optional[Dict] = None
_failed = False


def _config() -> Dict[str, float]:
    try:
        return {**DEFAULTS, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    except Exception:
        return dict(DEFAULTS)


def _build_index() -> Optional[Dict]:
    global _index, _failed
    if _index is not None or _failed:
        return _index
    with _lock:
        if _index is None and not _failed:
            try:
                texts, owners = [], []
                for i, item in enumerate(FAQ):
                    for lang in ("en", "ar"):
                        for q in item["q"][lang]:
                            texts.append(q)
                            owners.append(i)
                _index = {"vecs": ml_classifier.embed(texts), "owners": np.array(owners)}
            except Exception as e:
                log.warning("FAQ retrieval unavailable: %s", e)
                _failed = True
    return _index


def available() -> bool:
    return os.environ.get("RAG_ENABLED", "1") != "0" and _build_index() is not None


def scores(query: str) -> Optional[List[float]]:
    """Best cosine similarity per FAQ entry (max over its example questions)."""
    idx = _build_index()
    if idx is None:
        return None
    q = ml_classifier.embed([query])[0]
    sims = idx["vecs"] @ q
    best = np.full(len(FAQ), -1.0)
    for owner, s in zip(idx["owners"], sims):
        if s > best[owner]:
            best[owner] = s
    return best.tolist()


def answer(query: str, language: str = "en") -> Optional[Dict]:
    """Return an approved block, or None when nothing matches confidently."""
    if os.environ.get("RAG_ENABLED", "1") == "0":
        return None
    try:
        sc = scores(query)
    except Exception as e:
        log.warning("retrieval failed: %s", e)
        return None
    if sc is None:
        return None
    order = np.argsort(sc)[::-1]
    best, second = float(sc[order[0]]), float(sc[order[1]])
    cfg = _config()
    if best < cfg["min_score"] or best - second < cfg["min_margin"]:
        return None
    item = FAQ[int(order[0])]
    lang = language if language in ("en", "ar") else "en"
    return {"id": item["id"], "topic": item["q"][lang][0], "text": with_suffix(item["a"][lang], lang),
            "score": round(best, 3), "source": "approved_faq_v1"}


def reset_for_tests() -> None:
    global _index, _failed
    _index, _failed = None, False
