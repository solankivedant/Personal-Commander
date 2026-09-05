"""@tool decorator: JSON schema from type hints/docstring, tier (local/lan/net),
risk (safe/confirm/blocked), tags, undo registration. Phase 2."""

from __future__ import annotations

import inspect
import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

Tier = Literal["local", "lan", "net"]
Risk = Literal["safe", "confirm", "blocked"]

_TYPE_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


@dataclass(frozen=True)
class ToolSpec:
    """Everything the router, the LLM loop (Phase 4), and the security layer
    need to know about one registered tool. `schema` is what actually reaches
    the LLM's context — keep it and the wrapped function's docstring
    accurate, they are not just documentation.
    """

    name: str
    func: Callable[..., str]
    tier: Tier
    risk: Risk
    tags: tuple[str, ...]
    undo: str | None
    description: str
    schema: dict[str, Any]
    # Optional dry-run describer for `risk="confirm"` tools. Takes the same
    # arguments as the tool and returns what it *would* do, without doing it
    # — "I'll move 14 PDFs from Desktop to Documents/Invoices."
    #
    # security-and-privacy.md §8.2 requires the gate to speak a summary of
    # the real effect, and a schema-derived description cannot produce one:
    # only the tool can resolve "all the PDFs" into a count and a folder. A
    # gate that can only say "run move_files?" gives the user nothing to
    # catch a misroute with. Must never raise — same contract as the tool
    # body (see security/confirm.py's describe(), which guards it anyway).
    preview: Callable[..., str] | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        return self.func(*args, **kwargs)


class ToolRegistry:
    """Global tool registry. `blocked`-risk tools are stored here like any
    other tool (so security review and the audit log can still see them) but
    `iter_llm_visible()` excludes them — that is the structural
    unreachability security-and-privacy.md requires, not a prompt instruction
    a model could ignore.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool {spec.name!r} is already registered.")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def iter_llm_visible(self) -> list[ToolSpec]:
        """Tools reachable from the LLM tool-call path — everything except
        risk="blocked"."""
        return [t for t in self._tools.values() if t.risk != "blocked"]

    def clear(self) -> None:
        """Test-only: reset the registry between test modules that each
        import fresh tool modules."""
        self._tools.clear()


REGISTRY = ToolRegistry()


def _json_type_for(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _json_type_for(args[0])
        return {"anyOf": [_json_type_for(a) for a in args]}
    if origin is Literal:
        values = get_args(annotation)
        value_type = type(values[0]) if values else str
        return {"type": _TYPE_TO_JSON.get(value_type, "string"), "enum": list(values)}
    if origin in (list, tuple):
        item_args = get_args(annotation)
        item_type = item_args[0] if item_args else str
        return {"type": "array", "items": _json_type_for(item_type)}
    if isinstance(annotation, type) and annotation in _TYPE_TO_JSON:
        return {"type": _TYPE_TO_JSON[annotation]}
    return {"type": "string"}


def _parse_docstring(doc: str | None) -> tuple[str, dict[str, str]]:
    """Minimal Google-style docstring parser: the lines before an "Args:"
    section are the description; "name: text" lines under "Args:" become
    per-parameter descriptions. Deliberately not a dependency — the docstring
    format this project uses is small and stable (see
    .claude/skills/new-tool/SKILL.md).
    """
    if not doc:
        return "", {}
    lines = [ln.strip() for ln in doc.strip().splitlines()]
    description_lines: list[str] = []
    arg_docs: dict[str, str] = {}
    in_args = False
    for line in lines:
        if line.lower().rstrip() == "args:":
            in_args = True
            continue
        if not line:
            continue
        if in_args and ":" in line:
            name, _, text = line.partition(":")
            arg_docs[name.strip()] = text.strip()
        elif not in_args:
            description_lines.append(line)
    return " ".join(description_lines), arg_docs


def _build_schema(func: Callable[..., Any]) -> dict[str, Any]:
    hints = get_type_hints(func)
    hints.pop("return", None)
    sig = inspect.signature(func)
    _description, arg_docs = _parse_docstring(func.__doc__)

    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in sig.parameters.items():
        annotation = hints.get(param_name, str)
        prop = _json_type_for(annotation)
        if param_name in arg_docs:
            prop["description"] = arg_docs[param_name]
        properties[param_name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {"type": "object", "properties": properties, "required": required}


def tool(
    *,
    tier: Tier,
    risk: Risk,
    tags: list[str] | None = None,
    undo: str | None = None,
    preview: Callable[..., str] | None = None,
) -> Callable[[Callable[..., str]], Callable[..., str]]:
    """Register a function as a router/LLM-callable tool.

    tier: what the tool actually touches — local (never network), lan (this
          network only), or net (leaves the machine).
    risk: "safe" for everything else; "confirm" if it deletes, sends, spends,
          or overwrites; "blocked" if it touches credentials, the registry,
          or mass deletion (blocked tools never appear in
          ToolRegistry.iter_llm_visible()).
    undo: name of the function that reverses this tool's effect, if it
          mutates state. This is descriptive metadata for humans and the
          audit log — the tool body itself is responsible for pushing the
          actual inverse closure onto security.undo.UNDO_STACK before it
          mutates anything.
    preview: dry-run describer for confirm-risk tools; see ToolSpec.preview.
          Strongly recommended on anything whose effect depends on matching
          files or messages, where the argument list alone doesn't tell the
          user what is about to happen.
    """

    def decorator(func: Callable[..., str]) -> Callable[..., str]:
        description, _ = _parse_docstring(func.__doc__)
        spec = ToolSpec(
            name=func.__name__,
            func=func,
            tier=tier,
            risk=risk,
            tags=tuple(tags or ()),
            undo=undo,
            description=description or func.__name__,
            schema=_build_schema(func),
            preview=preview,
        )
        REGISTRY.register(spec)
        return func

    return decorator
