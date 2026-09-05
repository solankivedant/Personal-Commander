"""File search (Everything CLI), move, rename, delete. Tier 2. Phase 3.

Phase 3's deliverable is "safe to point at real files", so the safety
machinery here is the feature, not scaffolding around it:

- **Every path resolves inside `tools.files.roots`.** That list is the blast
  radius. A path that escapes it — absolute, `..`, or via a symlink, since
  containment is checked *after* `Path.resolve()` — is refused before any
  matching happens. Nothing here can touch `C:\\Windows`, `AppData`, or a
  folder the user did not name in config.
- **Batches are capped** at `tools.files.max_batch`. Past that the tool
  refuses and says so rather than confirming a hundred-file mutation, because
  mass deletion is `blocked` territory (security-and-privacy.md), not a
  bigger `confirm`.
- **Deletion goes to the Recycle Bin**, never `os.remove`. See
  `_undo_delete_files` for why that is also the undo story.
- **Mutating tools push their inverse before mutating**, and preview their
  real effect so the spoken confirmation names files and counts rather than
  argument values.

Parameter names are not free: the router passes grammar slots straight
through as `**kwargs`, so `query`/`source`/`destination`/`new_name` must keep
matching the templates in `config/intents/files.yaml`.

Indic file-type words ("tasveerein", "gaane") are not in `_TYPE_EXTENSIONS`
yet — spoken *folder* and *type* vocabulary in hi/gu is Phase 6 alongside the
rest of the Indic layer. The embedding examples route the intent correctly
today; a hi/gu query naming a type falls back to substring matching, which
degrades to "finds less", not "deletes something unexpected".
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable, Sequence, Sized
from pathlib import Path

from munshiji.security.undo import UNDO_STACK
from munshiji.tools.registry import tool

# Fallbacks mirroring config/default.yaml's `tools.files` section, which is
# the source of truth (engineering-standards.md: no behaviour constants in
# source). configure() syncs these at bootstrap; the values here only apply
# to a direct import in a unit test.
_ROOTS: tuple[str, ...] = (
    "~/Desktop",
    "~/Documents",
    "~/Downloads",
    "~/Pictures",
    "~/Music",
    "~/Videos",
)
_EVERYTHING_CLI = "es.exe"
_MAX_RESULTS = 20
_MAX_BATCH = 50
_SEARCH_TIMEOUT_S = 10
_WALK_MAX_ENTRIES = 20000


def configure(
    *,
    roots: Sequence[str] | None = None,
    everything_cli: str | None = None,
    max_results: int | None = None,
    max_batch: int | None = None,
    search_timeout_s: int | None = None,
    walk_max_entries: int | None = None,
) -> None:
    """Sync this module's tunables from `config.tools.files` at bootstrap."""
    global _ROOTS, _EVERYTHING_CLI, _MAX_RESULTS, _MAX_BATCH
    global _SEARCH_TIMEOUT_S, _WALK_MAX_ENTRIES
    if roots is not None:
        _ROOTS = tuple(roots)
    if everything_cli is not None:
        _EVERYTHING_CLI = everything_cli
    if max_results is not None:
        _MAX_RESULTS = max_results
    if max_batch is not None:
        _MAX_BATCH = max_batch
    if search_timeout_s is not None:
        _SEARCH_TIMEOUT_S = search_timeout_s
    if walk_max_entries is not None:
        _WALK_MAX_ENTRIES = walk_max_entries


class FileToolError(Exception):
    """A refusal with a sentence fit to speak aloud.

    Every tool below converts this to its return string. It exists so the
    safety checks can bail out from anywhere in a helper without each one
    threading an error value back up by hand — the `except FileToolError`
    at each tool boundary is what keeps the "tools never raise" contract.
    """


# ---------------------------------------------------------------------------
# Path safety. Everything else in this module goes through these.
# ---------------------------------------------------------------------------


def allowed_roots() -> list[Path]:
    """Configured roots, expanded and resolved. Non-existent ones are kept —
    they still define what is *addressable*, and a user with no ~/Music
    should get "I couldn't find that folder", not a path escape."""
    roots: list[Path] = []
    for raw in _ROOTS:
        try:
            roots.append(Path(os.path.expanduser(raw)).resolve())
        except OSError:
            continue
    return roots


def _is_within_roots(path: Path, roots: Iterable[Path]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def ensure_within_roots(path: Path) -> Path:
    """Resolve `path` and refuse it if it lands outside every allowed root.

    Resolution happens *before* the check, on purpose: `~/Desktop/../../Windows`
    and a symlink in Desktop pointing at `C:\\Windows` both normalize to
    something outside the roots, and a textual prefix check would pass both.
    """
    try:
        resolved = path.expanduser().resolve()
    except OSError as exc:
        raise FileToolError(f"I couldn't make sense of that path: {exc}") from exc

    roots = allowed_roots()
    if not _is_within_roots(resolved, roots):
        names = ", ".join(r.name for r in roots)
        raise FileToolError(
            f"I'm not allowed to touch {resolved}. I can only work inside your "
            f"{names} folders."
        )
    return resolved


# Spoken aliases for the configured roots. The roots themselves supply their
# own names (a root's folder name is automatically addressable), so this only
# holds the extra ways people say them.
_FOLDER_ALIASES: dict[str, str] = {
    "docs": "Documents",
    "document": "Documents",
    "my documents": "Documents",
    "download": "Downloads",
    "downloads folder": "Downloads",
    "pics": "Pictures",
    "pictures folder": "Pictures",
    "photos": "Pictures",
    "images": "Pictures",
    "desktop folder": "Desktop",
    "music folder": "Music",
    "songs": "Music",
    "videos folder": "Videos",
    "movies": "Videos",
}


def resolve_folder(name: str | None) -> Path | None:
    """Turn a spoken folder name into a real, allowed path.

    Accepts a root's own name ("desktop"), a common alias ("my documents"), a
    subfolder ("documents/invoices" or just "invoices"), or an absolute path.
    Returns None for None — callers read that as "search everywhere allowed".
    """
    if name is None:
        return None
    cleaned = name.strip().strip("\"'")
    if not cleaned:
        return None

    roots = allowed_roots()
    lowered = cleaned.lower()

    canonical = _FOLDER_ALIASES.get(lowered)
    for root in roots:
        if root.name.lower() == lowered or (canonical and root.name == canonical):
            return root

    candidate = Path(os.path.expanduser(cleaned))
    if candidate.is_absolute():
        return ensure_within_roots(candidate)

    # Relative: try under each root, e.g. "invoices" -> ~/Documents/Invoices.
    for root in roots:
        possible = root / cleaned
        if possible.is_dir():
            return ensure_within_roots(possible)
    # Also allow "documents/invoices" spelled against a root name.
    head, _, tail = cleaned.replace("\\", "/").partition("/")
    if tail:
        base = resolve_folder(head)
        if base is not None:
            possible = base / tail
            if possible.is_dir():
                return ensure_within_roots(possible)

    raise FileToolError(
        f"I couldn't find a folder called {cleaned!r} in the places I'm allowed to look."
    )


# ---------------------------------------------------------------------------
# Spoken query -> glob patterns
# ---------------------------------------------------------------------------

# Spoken type words to file extensions. "screenshots" is handled separately
# below because it's a filename convention, not an extension.
_TYPE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "pdf": ("pdf",),
    "pdfs": ("pdf",),
    "doc": ("doc", "docx"),
    "docs": ("doc", "docx"),
    "word document": ("doc", "docx"),
    "word documents": ("doc", "docx"),
    "spreadsheet": ("xls", "xlsx", "csv"),
    "spreadsheets": ("xls", "xlsx", "csv"),
    "excel file": ("xls", "xlsx"),
    "excel files": ("xls", "xlsx"),
    "presentation": ("ppt", "pptx"),
    "presentations": ("ppt", "pptx"),
    "image": ("jpg", "jpeg", "png", "gif", "bmp", "webp"),
    "images": ("jpg", "jpeg", "png", "gif", "bmp", "webp"),
    "photo": ("jpg", "jpeg", "png", "heic"),
    "photos": ("jpg", "jpeg", "png", "heic"),
    "picture": ("jpg", "jpeg", "png"),
    "pictures": ("jpg", "jpeg", "png"),
    "video": ("mp4", "mkv", "avi", "mov"),
    "videos": ("mp4", "mkv", "avi", "mov"),
    "song": ("mp3", "wav", "m4a", "flac"),
    "songs": ("mp3", "wav", "m4a", "flac"),
    "music": ("mp3", "wav", "m4a", "flac"),
    "text file": ("txt",),
    "text files": ("txt",),
    "zip": ("zip", "rar", "7z"),
    "archive": ("zip", "rar", "7z"),
    "archives": ("zip", "rar", "7z"),
    "log": ("log",),
    "logs": ("log",),
}

# Words that carry no filtering meaning and would otherwise become part of a
# substring pattern ("all the pdfs" -> "*all*the*pdfs*", matching nothing).
_FILLER_WORDS = frozenset(
    {
        "all", "the", "my", "every", "any", "some", "files", "file",
        "of", "in", "from", "everything", "stuff", "them",
    }
)

# Queries made only of these mean "everything here" — "delete all files in
# downloads" strips to nothing once fillers are removed, and refusing it as
# unintelligible would be wrong: the user was perfectly clear. It becomes "*",
# and the safety comes from where it should — the batch cap, the confirmation
# prompt naming the count and folder, and the Recycle Bin.
_EVERYTHING_WORDS = frozenset({"files", "file", "everything", "all", "stuff", "them"})


def query_to_globs(query: str) -> list[str]:
    """Turn a spoken description of files into glob patterns.

    "all my pdfs" -> ["*.pdf"], "budget report" -> ["*budget*report*"].
    Returning globs rather than a regex keeps this auditable: what the tool
    will match is legible in the confirmation prompt.
    """
    cleaned = query.strip().strip("\"'").lower()
    if not cleaned:
        raise FileToolError("I need to know which files you mean.")

    # An explicit pattern or extension the user (or the LLM) already spelled.
    if "*" in cleaned or "?" in cleaned:
        return [cleaned]
    if cleaned.startswith("."):
        return [f"*{cleaned}"]

    words = [w for w in cleaned.replace(",", " ").split() if w]
    meaningful = [w for w in words if w not in _FILLER_WORDS]
    phrase = " ".join(meaningful)

    if phrase in _TYPE_EXTENSIONS:
        return [f"*.{ext}" for ext in _TYPE_EXTENSIONS[phrase]]
    if "screenshot" in phrase:
        return ["*screenshot*"]

    # A trailing type word with qualifiers: "old logs", "last week's pdfs".
    if meaningful and meaningful[-1] in _TYPE_EXTENSIONS:
        extensions = _TYPE_EXTENSIONS[meaningful[-1]]
        qualifiers = meaningful[:-1]
        if not qualifiers:
            return [f"*.{ext}" for ext in extensions]
        stem = "*".join(qualifiers)
        return [f"*{stem}*.{ext}" for ext in extensions]

    if not meaningful:
        if any(word in _EVERYTHING_WORDS for word in words):
            return ["*"]
        raise FileToolError("I need to know which files you mean.")

    globs = ["*" + "*".join(meaningful) + "*"]
    # People say plurals; filenames are usually singular. "find my invoices"
    # must match "invoice a.pdf" — a literal substring match on "invoices"
    # finds nothing, which reads as a broken assistant rather than a naming
    # mismatch. Search dedupes, so offering both costs nothing.
    singular = [_depluralize(word) for word in meaningful]
    if singular != meaningful:
        globs.append("*" + "*".join(singular) + "*")
    return globs


def _depluralize(word: str) -> str:
    """Crude English de-pluralization, used only to widen a search.

    Deliberately not a stemmer: a wrong guess here can only add a pattern
    that matches nothing, never remove a correct one, so the simplest rule
    that covers "invoices"/"reports"/"photos" is the right amount of
    machinery.
    """
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("es") and word[-3] in "sxzh":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


# ---------------------------------------------------------------------------
# Search boundary. Isolated so tests can mock Everything/the filesystem.
# ---------------------------------------------------------------------------


def _run_everything(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=_SEARCH_TIMEOUT_S,
        check=False,
    )


def _everything_available() -> bool:
    return shutil.which(_EVERYTHING_CLI) is not None or Path(_EVERYTHING_CLI).is_file()


def _everything_search(root: Path, globs: Sequence[str], limit: int) -> list[Path] | None:
    """Query the Everything CLI. Returns None when it can't be used, which is
    the signal to fall back to a walk — distinct from "ran and found
    nothing" ([]), because those must not be confused."""
    if not _everything_available():
        return None
    # Everything treats "|" as OR between search terms.
    query = "|".join(globs)
    try:
        result = _run_everything(
            [_EVERYTHING_CLI, "-path", str(root), "-n", str(limit), query]
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    found: list[Path] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            found.append(Path(line))
    return found


def _walk_search(root: Path, globs: Sequence[str], limit: int) -> list[Path]:
    """Fallback when Everything isn't installed or its service is stopped.

    Bounded by `walk_max_entries` so a missing Everything degrades to slow
    rather than to a hung voice loop with no way to interrupt it.
    """
    found: list[Path] = []
    scanned = 0
    for pattern in globs:
        try:
            for path in root.rglob(pattern):
                scanned += 1
                if scanned > _WALK_MAX_ENTRIES:
                    return found
                if path.is_file():
                    found.append(path)
                    if len(found) >= limit:
                        return found
        except OSError:
            continue
    return found


def search_files(globs: Sequence[str], folder: Path | None, limit: int) -> list[Path]:
    """Find files matching `globs`, restricted to `folder` or all roots.

    Results are re-checked against the roots before being returned. Everything
    indexes the whole machine and a stale index can name a path that has since
    moved, so its output is treated as untrusted input to the containment
    check rather than as already-safe.
    """
    targets = [folder] if folder is not None else allowed_roots()
    seen: set[Path] = set()
    results: list[Path] = []
    for root in targets:
        if not root.is_dir():
            continue
        found = _everything_search(root, globs, limit)
        # Fall back to the walk when Everything is unusable (None) *and* when
        # it reports nothing (empty). Its index updates asynchronously, so a
        # file created or moved seconds ago is routinely absent from it — and
        # "the file I just saved" is exactly what someone asks a voice
        # assistant about. Trusting an empty result would make the tool
        # intermittently blind in the one case it is most used for. Non-empty
        # results are trusted as-is, so the common path stays instant.
        if not found:
            found = _walk_search(root, globs, limit)
        for path in found:
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in seen or not resolved.is_file():
                continue
            if not _is_within_roots(resolved, allowed_roots()):
                continue
            seen.add(resolved)
            results.append(resolved)
    results.sort(key=lambda p: str(p).lower())
    return results


def _describe_count(items: Sized, noun: str = "file") -> str:
    """Pluralize a count for speech. Takes anything sized, because callers
    count both matched paths and completed (source, destination) moves."""
    count = len(items)
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _check_batch(paths: Sequence[Path], verb: str) -> None:
    if not paths:
        raise FileToolError("I couldn't find any files matching that.")
    if len(paths) > _MAX_BATCH:
        raise FileToolError(
            f"That matches {len(paths)} files, which is more than I'll {verb} at once "
            f"(limit {_MAX_BATCH}). Narrow it down and ask again."
        )


def _unique_destination(directory: Path, name: str) -> Path:
    """Never silently overwrite. "report.pdf" becomes "report (2).pdf"."""
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    for counter in range(2, 1000):
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
    raise FileToolError(f"There are already too many files named like {name!r}.")


# ---------------------------------------------------------------------------
# Recycle Bin boundary
# ---------------------------------------------------------------------------


def _recycle(paths: Sequence[Path]) -> None:
    """Delete via the shell with FOF_ALLOWUNDO, i.e. to the Recycle Bin.

    Never `os.remove`. The Recycle Bin is what makes a misheard delete
    recoverable, and it is the reason `delete_files` can be a `confirm` tool
    rather than a `blocked` one.
    """
    from win32com.shell import shell, shellcon  # type: ignore[import-untyped]

    # pFrom is a double-NUL-terminated, NUL-separated list.
    joined = "\0".join(str(p) for p in paths) + "\0\0"
    flags = shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION | shellcon.FOF_SILENT
    result, aborted = shell.SHFileOperation(
        (0, shellcon.FO_DELETE, joined, None, flags, None, None)
    )
    if result != 0:
        raise OSError(f"Shell delete failed with code {result}.")
    if aborted:
        raise OSError("The delete was aborted before it finished.")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(tier="local", risk="safe", tags=["files"])
def find_file(query: str, folder: str | None = None) -> str:
    """Search for files by name or type in the user's document folders.

    Args:
        query: What to look for, e.g. 'budget report' or 'all pdfs'.
        folder: Optional folder to limit the search to, e.g. 'Downloads'.
    """
    try:
        globs = query_to_globs(query)
        target = resolve_folder(folder)
        matches = search_files(globs, target, _MAX_RESULTS)
    except FileToolError as exc:
        return str(exc)
    except Exception as exc:
        return f"Could not search for files: {exc}"

    if not matches:
        where = f" in {target.name}" if target else ""
        return f"I couldn't find anything matching {query!r}{where}."

    shown = matches[: min(5, _MAX_RESULTS)]
    listed = "; ".join(f"{p.name} in {p.parent.name}" for p in shown)
    if len(matches) > len(shown):
        return f"Found {_describe_count(matches)}. The first {len(shown)}: {listed}."
    return f"Found {_describe_count(matches)}: {listed}."


def _preview_move_files(query: str, destination: str, source: str | None = None) -> str:
    globs = query_to_globs(query)
    target = resolve_folder(source)
    dest = resolve_folder(destination)
    if dest is None:
        raise FileToolError("I need to know where to move them.")
    matches = search_files(globs, target, _MAX_BATCH + 1)
    _check_batch(matches, "move")
    where = target.name if target else "your folders"
    return f"Move {_describe_count(matches)} from {where} to {dest.name}"


@tool(
    tier="local",
    risk="confirm",
    tags=["files"],
    undo="_undo_move_files",
    preview=_preview_move_files,
)
def move_files(query: str, destination: str, source: str | None = None) -> str:
    """Move files matching a description into another folder.

    Args:
        query: Which files to move, e.g. 'all pdfs'.
        destination: Folder to move them into, e.g. 'Documents'.
        source: Optional folder to move them from, e.g. 'Desktop'.
    """
    try:
        globs = query_to_globs(query)
        target = resolve_folder(source)
        dest = resolve_folder(destination)
        if dest is None:
            return "I need to know where to move them."
        matches = search_files(globs, target, _MAX_BATCH + 1)
        _check_batch(matches, "move")
        if not dest.is_dir():
            return f"{dest.name} isn't a folder I can move things into."
    except FileToolError as exc:
        return str(exc)
    except Exception as exc:
        return f"Could not work out which files to move: {exc}"

    moved: list[tuple[Path, Path]] = []
    UNDO_STACK.push(
        "move_files",
        f"Move {_describe_count(matches)} back out of {dest.name}",
        lambda: _undo_move_files(moved),
    )
    failures = 0
    for path in matches:
        try:
            final = _unique_destination(dest, path.name)
            shutil.move(str(path), str(final))
            moved.append((path, final))
        except (OSError, FileToolError):
            failures += 1

    if not moved:
        return f"I couldn't move anything into {dest.name}."
    suffix = f" ({failures} couldn't be moved.)" if failures else ""
    return f"Moved {_describe_count(moved)} to {dest.name}.{suffix}"


def _undo_move_files(moved: list[tuple[Path, Path]]) -> str:
    """Real inverse: put each file back where it came from."""
    restored = 0
    for original, current in reversed(moved):
        try:
            if current.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(current), str(original))
                restored += 1
        except OSError:
            continue
    if not restored:
        return "I couldn't move those files back."
    return f"Moved {restored} file{'s' if restored != 1 else ''} back."


def _preview_rename_file(query: str, new_name: str) -> str:
    globs = query_to_globs(query)
    matches = search_files(globs, None, 2)
    if not matches:
        raise FileToolError(f"I couldn't find a file matching {query!r}.")
    if len(matches) > 1:
        raise FileToolError(
            f"{query!r} matches more than one file, so I don't know which to rename."
        )
    return f"Rename {matches[0].name} in {matches[0].parent.name} to {new_name}"


@tool(
    tier="local",
    risk="confirm",
    tags=["files"],
    undo="_undo_rename_file",
    preview=_preview_rename_file,
)
def rename_file(query: str, new_name: str) -> str:
    """Rename a single file.

    Args:
        query: Which file to rename, e.g. 'budget report'.
        new_name: The new filename, e.g. 'budget 2026.xlsx'.
    """
    try:
        cleaned = new_name.strip().strip("\"'")
        if not cleaned:
            return "I need a new name for it."
        # A rename must not become a move: reject separators outright rather
        # than resolving them, so "../../Windows/evil.exe" can't get through.
        if any(sep in cleaned for sep in ("/", "\\", ":")):
            return "A new name can't contain a folder path."
        globs = query_to_globs(query)
        matches = search_files(globs, None, 2)
        if not matches:
            return f"I couldn't find a file matching {query!r}."
        if len(matches) > 1:
            return f"{query!r} matches more than one file, so I'm not sure which to rename."
        original = ensure_within_roots(matches[0])
        if not Path(cleaned).suffix and original.suffix:
            cleaned = cleaned + original.suffix
        destination = ensure_within_roots(original.parent / cleaned)
        if destination.exists():
            return f"There's already a file called {cleaned} there."
    except FileToolError as exc:
        return str(exc)
    except Exception as exc:
        return f"Could not work out which file to rename: {exc}"

    UNDO_STACK.push(
        "rename_file",
        f"Rename {cleaned} back to {original.name}",
        lambda: _undo_rename_file(destination, original),
    )
    try:
        original.rename(destination)
    except OSError as exc:
        return f"Could not rename {original.name}: {exc}"
    return f"Renamed {original.name} to {cleaned}."


def _undo_rename_file(current: Path, original: Path) -> str:
    """Real inverse: rename it back."""
    try:
        if not current.exists():
            return f"{current.name} isn't there any more, so I couldn't undo the rename."
        current.rename(original)
        return f"Renamed {current.name} back to {original.name}."
    except OSError as exc:
        return f"Could not undo the rename: {exc}"


def _preview_delete_files(query: str, folder: str | None = None) -> str:
    globs = query_to_globs(query)
    target = resolve_folder(folder)
    matches = search_files(globs, target, _MAX_BATCH + 1)
    _check_batch(matches, "delete")
    where = target.name if target else "your folders"
    names = ", ".join(p.name for p in matches[:3])
    tail = ", and others" if len(matches) > 3 else ""
    return f"Move {_describe_count(matches)} from {where} to the Recycle Bin ({names}{tail})"


@tool(
    tier="local",
    risk="confirm",
    tags=["files"],
    undo="_undo_delete_files",
    preview=_preview_delete_files,
)
def delete_files(query: str, folder: str | None = None) -> str:
    """Move files matching a description to the Recycle Bin.

    Args:
        query: Which files to delete, e.g. 'old logs'.
        folder: Optional folder to delete them from, e.g. 'Downloads'.
    """
    try:
        globs = query_to_globs(query)
        target = resolve_folder(folder)
        matches = search_files(globs, target, _MAX_BATCH + 1)
        _check_batch(matches, "delete")
    except FileToolError as exc:
        return str(exc)
    except Exception as exc:
        return f"Could not work out which files to delete: {exc}"

    UNDO_STACK.push(
        "delete_files",
        f"Recover {_describe_count(matches)} from the Recycle Bin",
        lambda: _undo_delete_files(list(matches)),
    )
    try:
        _recycle(matches)
    except Exception as exc:
        return f"Could not delete those files: {exc}"
    return (
        f"Moved {_describe_count(matches)} to the Recycle Bin. "
        "Say 'undo that' if you didn't mean it."
    )


def _undo_delete_files(paths: list[Path]) -> str:
    """Guided recovery rather than an automatic restore, and deliberately so.

    Windows exposes no supported API for restoring a specific item from the
    Recycle Bin. It can be driven through the shell namespace, but items there
    are identified by an internal `$R…` path — the original path is only
    available as a localized "Original Location" detail column, so matching on
    it breaks on a non-English Windows and on any version that reorders the
    columns. Building the mutating half of undo on that would be worse than
    not having it.

    So the trade is explicit: `delete_files` never destroys anything (the
    Recycle Bin is the safety net, which is what lets this be `confirm` rather
    than `blocked`), and undo tells the user exactly what to recover and
    where. `move_files` and `rename_file` are plain filesystem operations with
    no such constraint, and both undo automatically.
    """
    if not paths:
        return "There's nothing to recover."
    names = ", ".join(p.name for p in paths[:3])
    tail = " and others" if len(paths) > 3 else ""
    return (
        f"{_describe_count(paths)} ({names}{tail}) went to the Recycle Bin and are still "
        "there. Open it to restore them — Windows can't put them back from here."
    )
