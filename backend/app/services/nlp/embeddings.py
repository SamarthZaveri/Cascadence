from functools import lru_cache
from pathlib import Path

from sentence_transformers import SentenceTransformer

from app.config import get_settings


@lru_cache
def embedding_model():
    path = Path(get_settings().NLP_CACHE_DIR) / "minilm"
    if not (path / "modules.json").exists():
        raise RuntimeError("MiniLM model missing. Run python -m app.services.nlp.setup first")
    return SentenceTransformer(str(path), device="cpu", local_files_only=True)


def embed_text(texts: list[str]):
    return embedding_model().encode(
        texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    )
