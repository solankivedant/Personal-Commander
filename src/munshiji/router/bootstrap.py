"""Assembles the Phase 2 cascade from config: grammar over config/intents,
embeddings over config/examples, slot extraction, and the tool modules whose
import registers them.

Lives here rather than in `__main__` because there is now more than one way
to run the engine — the voice loop and the Control Center (`ui/server.py`,
started with `python -m munshiji --no-voice`) both need an identically built
router, and neither should be able to drift from the other. Importing
`__main__` to get it is not an option: that module pulls in PySide6, the
audio stack and Whisper.
"""

from __future__ import annotations

from pathlib import Path

from munshiji.config import MunshijiConfig
from munshiji.router import slots as router_slots
from munshiji.router.embeddings import EmbeddingIndex, SentenceTransformerEncoder
from munshiji.router.grammar import GrammarRouter
from munshiji.router.router import Router
from munshiji.security.undo import UNDO_STACK
from munshiji.tools import apps as app_tools
from munshiji.tools import files as file_tools
from munshiji.tools import system as system_tools
from munshiji.tools.apps import build_app_index

REPO_ROOT = Path(__file__).resolve().parents[3]


def configure_tools(config: MunshijiConfig) -> None:
    """Push every YAML-owned behaviour constant into the tool modules.

    `system_tools`/`app_tools`/`file_tools` are imported for their `@tool`
    registration side effects as much as for these calls — REGISTRY needs
    them loaded before any route can be resolved.
    """
    system_tools.configure(
        volume_step_pct=config.tools.volume_step_pct,
        brightness_step_pct=config.tools.brightness_step_pct,
        subprocess_timeout_s=config.tools.subprocess_timeout_s,
    )
    app_tools.configure(fuzzy_cutoff=config.tools.fuzzy_app_cutoff)
    file_tools.configure(
        roots=config.tools.files.roots,
        everything_cli=config.tools.files.everything_cli,
        max_results=config.tools.files.max_results,
        max_batch=config.tools.files.max_batch,
        search_timeout_s=config.tools.files.search_timeout_s,
        walk_max_entries=config.tools.files.walk_max_entries,
    )
    router_slots.configure(fuzzy_app_cutoff=config.router.slots.fuzzy_app_cutoff)
    UNDO_STACK.configure(max_depth=config.security.undo_depth)


def build_router(config: MunshijiConfig, root: Path = REPO_ROOT) -> Router:
    """Configure the tools, then assemble the grammar -> embeddings cascade."""
    configure_tools(config)

    grammar = GrammarRouter.from_config_dirs(
        config.router.grammar.dirs,
        root=root,
        level_range=config.router.grammar.level_range,
    )

    # config/default.yaml names the model by its short HF handle
    # ("multilingual-e5-small"); SentenceTransformerEncoder needs the full
    # "org/name" id it actually publishes under.
    model_name = config.router.embeddings.model
    if "/" not in model_name:
        model_name = f"intfloat/{model_name}"
    embeddings = EmbeddingIndex(SentenceTransformerEncoder(model_name))
    embeddings.build_from_dirs([root / config.router.embeddings.examples])

    known_apps = tuple(build_app_index().keys())
    return Router(
        grammar,
        embeddings,
        config.router,
        known_apps=known_apps or router_slots.DEFAULT_KNOWN_APPS,
    )
