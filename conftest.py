"""Test configuration: legacy header auth is enabled for tests only (production uses signed bearer tokens)."""
import os

os.environ.setdefault("ALLOW_HEADER_AUTH", "1")
# Keyword-rule tests must be deterministic and fast: the embedding model is switched on explicitly in
# tests that exercise it (see eval/test_ml_classifier.py).
os.environ.setdefault("SAFETY_ML", "0")
os.environ.setdefault("RAG_ENABLED", "0")  # FAQ retrieval is switched on explicitly in eval/test_rag.py
