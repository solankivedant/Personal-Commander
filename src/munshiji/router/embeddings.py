"""Stage 2: multilingual-e5-small embedding index, cosine nearest-neighbour
at threshold 0.75 (from config, not hardcoded).

Examples live in ``config/examples/{en,hi,gu}.jsonl`` — one shared example
set per intent, deliberately not per-language, because the multilingual
encoder places semantically equivalent en/hi/gu phrasings in the same
vector neighbourhood (see .claude/rules/architecture-and-router.md). The
encoder itself is injectable so tests can run against a small deterministic
fake instead of downloading the ~470MB real model — this sandbox has no
network access for that pull, so `tests/test_router.py` must never construct
`SentenceTransformerEncoder` by default.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

REPO_ROOT = Path(__file__).resolve().parents[3]

FloatArray = npt.NDArray[np.float32]

# Real sentence-transformers model this encodes with in production —
# recorded here for the classmethod default and in docs/LICENSING-AUDIT.md
# (MIT), not duplicated as an unexplained magic string.
DEFAULT_MODEL_NAME = "intfloat/multilingual-e5-small"

# e5 models are trained with a "query: " / "passage: " prefix convention.
# Both index-building and querying use "query: " here since this is a
# symmetric similarity match (utterance vs. example utterance), not
# asymmetric retrieval.
_E5_PREFIX = "query: "

Encoder = Callable[[Sequence[str]], FloatArray]


@dataclass(frozen=True)
class ExampleEntry:
    text: str
    intent: str
    args: dict[str, Any]
    lang: str


@dataclass(frozen=True)
class EmbeddingMatch:
    intent: str
    args: dict[str, Any]
    score: float
    example_text: str
    lang: str


class SentenceTransformerEncoder:
    """Default production encoder: real sentence-transformers weights.

    Lazily imports `sentence_transformers` so importing this module (and
    therefore the router) never requires the dependency or a model download
    unless this class is actually instantiated.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def __call__(self, texts: Sequence[str]) -> FloatArray:
        prefixed = [f"{_E5_PREFIX}{t}" for t in texts]
        embeddings = self._model.encode(prefixed, normalize_embeddings=True)
        return np.asarray(embeddings, dtype=np.float32)


def _normalize(vectors: FloatArray) -> FloatArray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    result: FloatArray = vectors / norms
    return result


def load_examples(paths: Iterable[Path]) -> list[ExampleEntry]:
    """Load `{"text", "intent", "args"}` JSONL example files. The filename
    stem (en/hi/gu) is recorded as the entry's language for reporting, but
    matching itself is language-agnostic — that's the whole point of a
    multilingual encoder."""
    entries: list[ExampleEntry] = []
    for path in sorted(paths):
        lang = path.stem
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_no}: invalid JSON — {exc}") from exc
                entries.append(
                    ExampleEntry(
                        text=obj["text"],
                        intent=obj["intent"],
                        args=obj.get("args", {}),
                        lang=lang,
                    )
                )
    return entries


class EmbeddingIndex:
    """Cosine nearest-neighbour index over example utterances."""

    def __init__(self, encoder: Encoder) -> None:
        self._encoder = encoder
        self._entries: list[ExampleEntry] = []
        self._vectors: FloatArray = np.zeros((0, 0), dtype=np.float32)

    @property
    def entries(self) -> list[ExampleEntry]:
        return list(self._entries)

    def build_from_examples(self, entries: Sequence[ExampleEntry]) -> None:
        self._entries = list(entries)
        if not self._entries:
            self._vectors = np.zeros((0, 0), dtype=np.float32)
            return
        raw = np.asarray(self._encoder([e.text for e in self._entries]), dtype=np.float32)
        self._vectors = _normalize(raw)

    def build_from_dirs(self, dirs: Iterable[Path]) -> None:
        paths: list[Path] = []
        for d in dirs:
            paths.extend(d.glob("*.jsonl"))
        self.build_from_examples(load_examples(paths))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            path,
            vectors=self._vectors,
            texts=np.array([e.text for e in self._entries], dtype=object),
            intents=np.array([e.intent for e in self._entries], dtype=object),
            args=np.array([json.dumps(e.args) for e in self._entries], dtype=object),
            langs=np.array([e.lang for e in self._entries], dtype=object),
            allow_pickle=True,
        )

    @classmethod
    def load(cls, path: Path, encoder: Encoder) -> EmbeddingIndex:
        index = cls(encoder)
        with np.load(path, allow_pickle=True) as data:
            index._vectors = data["vectors"].astype(np.float32)
            index._entries = [
                ExampleEntry(text=t, intent=i, args=json.loads(a), lang=lang)
                for t, i, a, lang in zip(
                    data["texts"], data["intents"], data["args"], data["langs"], strict=True
                )
            ]
        return index

    def match(self, text: str, threshold: float) -> EmbeddingMatch | None:
        if self._vectors.shape[0] == 0:
            return None
        query = np.asarray(self._encoder([text]), dtype=np.float32)
        query = _normalize(query)[0]
        sims = self._vectors @ query
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])
        if best_score < threshold:
            return None
        entry = self._entries[best_idx]
        return EmbeddingMatch(
            intent=entry.intent,
            args=dict(entry.args),
            score=best_score,
            example_text=entry.text,
            lang=entry.lang,
        )
