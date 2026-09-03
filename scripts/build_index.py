"""Rebuild the embedding index from config/examples/*.jsonl.

Run after any intent or example change:

    uv run python scripts/build_index.py

Also importable so `router/teach.py` can rebuild the index in-process right
after appending a new example, without shelling out.
"""

from __future__ import annotations

from pathlib import Path

from munshiji.router.embeddings import EmbeddingIndex, Encoder, SentenceTransformerEncoder

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLES_DIR = REPO_ROOT / "config" / "examples"
DEFAULT_INDEX_PATH = REPO_ROOT / "data" / "router_index.npz"


def build_index(
    examples_dir: Path = DEFAULT_EXAMPLES_DIR,
    index_path: Path = DEFAULT_INDEX_PATH,
    encoder: Encoder | None = None,
) -> EmbeddingIndex:
    """Build (and persist) the embedding index from a directory of
    `{lang}.jsonl` example files. `encoder` is injectable so tests/CI can
    pass a small deterministic fake instead of downloading the real
    ~470MB multilingual-e5-small weights — production callers should leave
    it as None to get the real SentenceTransformerEncoder."""
    active_encoder: Encoder = encoder if encoder is not None else SentenceTransformerEncoder()
    index = EmbeddingIndex(active_encoder)
    index.build_from_dirs([examples_dir])
    index.save(index_path)
    return index


def main() -> None:
    index = build_index()
    print(
        f"Built embedding index: {len(index.entries)} examples -> {DEFAULT_INDEX_PATH}"
    )


if __name__ == "__main__":
    main()
