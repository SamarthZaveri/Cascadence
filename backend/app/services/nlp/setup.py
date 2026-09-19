"""Explicit one-time learned-model downloads; runtime remains offline."""

import subprocess
import sys
from pathlib import Path

import spacy
from sentence_transformers import SentenceTransformer

from app.config import get_settings


def main():
    settings = get_settings()
    root = Path(settings.NLP_CACHE_DIR)
    root.mkdir(parents=True, exist_ok=True)
    if settings.NLP_SPACY_MODEL != "en_core_web_lg":
        raise ValueError("This phase provisions en_core_web_lg; change the contract first")
    if not (root / "spacy" / "config.cfg").exists():
        subprocess.run(
            [sys.executable, "-m", "spacy", "download", settings.NLP_SPACY_MODEL], check=True
        )
        spacy.load(settings.NLP_SPACY_MODEL).to_disk(root / "spacy")
    if not (root / "minilm" / "modules.json").exists():
        SentenceTransformer(settings.NLP_EMBEDDING_MODEL, device="cpu").save(str(root / "minilm"))
    SentenceTransformer(str(root / "minilm"), device="cpu", local_files_only=True)
    print("NLP models ready. Backend and worker share this cache.")


if __name__ == "__main__":
    main()
