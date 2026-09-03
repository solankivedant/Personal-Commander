"""Stage 4: teach mode.

Fires when both grammar (Stage 1) and embeddings (Stage 2) miss, and the LLM
(Stage 3, Phase 4) is disabled or also misses. In Phase 2 the LLM stage
doesn't exist yet, so `router.py` currently falls straight through to teach
mode whenever embeddings miss and `router.teach_mode` is enabled.

Appends the unmatched utterance to the relevant intent's example JSONL file
and rebuilds the embedding index so the *next* occurrence of a similar
phrasing is caught at Stage 2 instead of falling through again — this is
what makes the router "get faster with use" per CLAUDE.md rather than
escalating the same miss forever.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from munshiji.router.embeddings import EmbeddingIndex, Encoder

REPO_ROOT = Path(__file__).resolve().parents[3]


def teach(
    text: str,
    intent: str,
    args: dict[str, Any],
    lang: str,
    examples_dir: Path,
) -> Path:
    """Append one new example line to `{examples_dir}/{lang}.jsonl`.

    Creates the file if this is the first taught example in that language.
    Does not rebuild the index itself — call `rebuild_index_after_teach`
    (or `scripts/build_index.py`) once teaching is done, since a caller may
    want to batch several taught utterances before paying the rebuild cost.
    """
    examples_dir.mkdir(parents=True, exist_ok=True)
    path = examples_dir / f"{lang}.jsonl"
    entry = {"text": text, "intent": intent, "args": args}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def rebuild_index_after_teach(
    examples_dir: Path,
    index_path: Path,
    encoder: Encoder,
) -> EmbeddingIndex:
    """Rebuild the embedding index in-process (no subprocess) after one or
    more `teach()` calls. Shares the exact build logic scripts/build_index.py
    uses so the two never drift."""
    index = EmbeddingIndex(encoder)
    index.build_from_dirs([examples_dir])
    index.save(index_path)
    return index
