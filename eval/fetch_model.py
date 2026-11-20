"""Download the embedding model once (about 220 MB) into models/fastembed, then print a sanity check.

Usage:  pip install -r requirements-ml.txt && python -m eval.fetch_model
"""
from backend.ml_classifier import CACHE_DIR, MODEL_NAME, embed

if __name__ == "__main__":
    vecs = embed(["hello", "مرحبا"])
    print(f"Model {MODEL_NAME} ready in {CACHE_DIR}; embedding size {vecs.shape[1]}")
