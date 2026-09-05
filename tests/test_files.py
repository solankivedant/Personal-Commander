"""File tool tests: path containment, query parsing, move/rename/delete, undo.

Every test runs against a temporary sandbox configured as the tool's allowed
roots, so nothing here touches the real Desktop/Documents. The Recycle Bin
boundary (`files._recycle`) is monkeypatched by default — a unit test must not
put things in the user's actual Recycle Bin — and the Everything CLI boundary
is patched where a test needs to pin which search backend is exercised.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from munshiji.security.undo import UNDO_STACK
from munshiji.tools import files
from munshiji.tools.registry import REGISTRY


@pytest.fixture(autouse=True)
def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Point the file tools at a temp tree and restore the real config after."""
    desktop = tmp_path / "Desktop"
    documents = tmp_path / "Documents"
    downloads = tmp_path / "Downloads"
    for folder in (desktop, documents, downloads):
        folder.mkdir()

    original = (
        files._ROOTS,
        files._EVERYTHING_CLI,
        files._MAX_RESULTS,
        files._MAX_BATCH,
        files._SEARCH_TIMEOUT_S,
        files._WALK_MAX_ENTRIES,
    )
    files.configure(
        roots=[str(desktop), str(documents), str(downloads)],
        everything_cli="es.exe",
        max_results=20,
        max_batch=50,
        search_timeout_s=5,
        walk_max_entries=20000,
    )
    UNDO_STACK.clear()
    yield tmp_path
    UNDO_STACK.clear()
    (
        files._ROOTS,
        files._EVERYTHING_CLI,
        files._MAX_RESULTS,
        files._MAX_BATCH,
        files._SEARCH_TIMEOUT_S,
        files._WALK_MAX_ENTRIES,
    ) = original


@pytest.fixture(autouse=True)
def _no_real_recycle_bin(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Delete by unlinking instead of recycling.

    The tools must never be able to put a test file in the developer's real
    Recycle Bin. A test that wants to assert the shell call itself patches
    this again with its own recorder.
    """

    def fake_recycle(paths: Any) -> None:
        for path in paths:
            Path(path).unlink()

    monkeypatch.setattr(files, "_recycle", fake_recycle)


def _make(folder: Path, *names: str) -> list[Path]:
    created = []
    for name in names:
        path = folder / name
        path.write_text("x", encoding="utf-8")
        created.append(path)
    return created


# ---------------------------------------------------------------------------
# Path containment — the blast-radius cap
# ---------------------------------------------------------------------------


def test_absolute_path_outside_roots_is_refused(_sandbox: Path) -> None:
    with pytest.raises(files.FileToolError):
        files.ensure_within_roots(Path("C:/Windows/System32"))


def test_parent_traversal_is_refused(_sandbox: Path) -> None:
    """`..` is normalized before the check, so it cannot climb out."""
    with pytest.raises(files.FileToolError):
        files.ensure_within_roots(_sandbox / "Desktop" / ".." / ".." / "elsewhere")


def test_symlink_pointing_outside_roots_is_refused(
    _sandbox: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Containment is checked after resolve(), so a symlink inside a root that
    points outside it is caught. A textual prefix check would pass this."""
    outside = tmp_path_factory.mktemp("outside")
    link = _sandbox / "Desktop" / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation needs Developer Mode or admin on Windows")
    with pytest.raises(files.FileToolError):
        files.ensure_within_roots(link / "secrets.txt")


def test_move_to_path_outside_roots_is_refused(_sandbox: Path) -> None:
    _make(_sandbox / "Desktop", "a.pdf")
    result = files.move_files("all pdfs", r"C:\Windows")
    assert "not allowed" in result.lower()
    assert (_sandbox / "Desktop" / "a.pdf").exists()


def test_rename_cannot_become_a_move(_sandbox: Path) -> None:
    """A path separator in the new name is rejected outright rather than
    resolved — "../../Windows/evil.exe" must not be a rename target."""
    _make(_sandbox / "Desktop", "notes.txt")
    result = files.rename_file("notes", "../../evil.txt")
    assert "folder path" in result
    assert (_sandbox / "Desktop" / "notes.txt").exists()


def test_search_results_are_re_checked_against_roots(
    _sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everything indexes the whole machine and its index can be stale, so its
    output is treated as untrusted input to the containment check."""
    outside = _sandbox / "not_a_root.txt"
    outside.write_text("x", encoding="utf-8")
    monkeypatch.setattr(files, "_everything_search", lambda *a, **k: [outside])
    monkeypatch.setattr(files, "_walk_search", lambda *a, **k: [outside])
    assert files.search_files(["*.txt"], None, 10) == []


# ---------------------------------------------------------------------------
# Spoken query -> globs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("all pdfs", ["*.pdf"]),
        ("pdfs", ["*.pdf"]),
        (".pdf", ["*.pdf"]),
        ("*.tmp", ["*.tmp"]),
        ("budget report", ["*budget*report*"]),
        ("old logs", ["*old*.log"]),
        ("screenshots", ["*screenshot*"]),
    ],
)
def test_query_to_globs(query: str, expected: list[str]) -> None:
    assert files.query_to_globs(query) == expected


def test_query_of_only_filler_words_means_everything() -> None:
    """"delete all files in downloads" strips to nothing once fillers go.
    That is a clear instruction, not an unintelligible one — the batch cap and
    the confirmation prompt are what make it safe."""
    assert files.query_to_globs("all files") == ["*"]
    assert files.query_to_globs("everything") == ["*"]


def test_empty_query_is_refused() -> None:
    with pytest.raises(files.FileToolError):
        files.query_to_globs("   ")


def test_photos_expands_to_several_extensions() -> None:
    assert set(files.query_to_globs("photos")) == {"*.jpg", "*.jpeg", "*.png", "*.heic"}


def test_plural_query_also_matches_singular_filenames() -> None:
    """People say plurals; filenames are usually singular. "find my invoices"
    finding nothing because the file is "invoice a.pdf" reads as a broken
    assistant, not a naming mismatch."""
    assert files.query_to_globs("my invoices") == ["*invoices*", "*invoice*"]
    assert files.query_to_globs("copies") == ["*copies*", "*copy*"]
    # No spurious variant when the word isn't a plural.
    assert files.query_to_globs("address") == ["*address*"]


def test_plural_widening_finds_singular_files(_sandbox: Path) -> None:
    _make(_sandbox / "Desktop", "invoice a.pdf", "invoice b.pdf")
    assert "2 files" in files.find_file("my invoices")


# ---------------------------------------------------------------------------
# Search backends
# ---------------------------------------------------------------------------


def test_walk_fallback_used_when_everything_unavailable(
    _sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make(_sandbox / "Desktop", "a.pdf")
    monkeypatch.setattr(files, "_everything_available", lambda: False)
    assert [p.name for p in files.search_files(["*.pdf"], None, 10)] == ["a.pdf"]


def test_empty_everything_result_falls_back_to_walk(
    _sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everything's index updates asynchronously, so a file created seconds
    ago is routinely missing from it. Treating its empty result as
    authoritative would make the tool blind to exactly the files people ask
    about most — the ones they just saved."""
    _make(_sandbox / "Desktop", "fresh.pdf")
    monkeypatch.setattr(files, "_everything_available", lambda: True)
    monkeypatch.setattr(files, "_everything_search", lambda *a, **k: [])
    assert [p.name for p in files.search_files(["*.pdf"], None, 10)] == ["fresh.pdf"]


def test_everything_failure_returns_none_not_empty(
    _sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"couldn't run" and "ran, found nothing" must stay distinguishable."""
    monkeypatch.setattr(files, "_everything_available", lambda: True)
    monkeypatch.setattr(
        files,
        "_run_everything",
        lambda args: subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="no"),
    )
    assert files._everything_search(_sandbox / "Desktop", ["*.pdf"], 10) is None


# ---------------------------------------------------------------------------
# find_file
# ---------------------------------------------------------------------------


def test_find_file_reports_matches(_sandbox: Path) -> None:
    _make(_sandbox / "Desktop", "a.pdf", "b.pdf")
    result = files.find_file("all pdfs")
    assert "2 files" in result and "a.pdf" in result


def test_find_file_no_match_is_a_sentence_not_an_error(_sandbox: Path) -> None:
    assert "couldn't find" in files.find_file("nothing like this exists")


def test_find_file_scoped_to_folder(_sandbox: Path) -> None:
    _make(_sandbox / "Desktop", "desk.pdf")
    _make(_sandbox / "Downloads", "down.pdf")
    result = files.find_file("all pdfs", folder="Downloads")
    assert "down.pdf" in result and "desk.pdf" not in result


def test_unknown_folder_is_refused(_sandbox: Path) -> None:
    assert "couldn't find a folder" in files.find_file("all pdfs", folder="Nonexistent")


# ---------------------------------------------------------------------------
# move_files + undo
# ---------------------------------------------------------------------------


def test_move_files_moves_and_undo_restores(_sandbox: Path) -> None:
    desktop, documents = _sandbox / "Desktop", _sandbox / "Documents"
    _make(desktop, "a.pdf", "b.pdf", "keep.txt")

    result = files.move_files("all pdfs", "Documents", "Desktop")
    assert "Moved 2 files" in result
    assert sorted(p.name for p in documents.iterdir()) == ["a.pdf", "b.pdf"]
    assert [p.name for p in desktop.iterdir()] == ["keep.txt"]

    assert "back" in UNDO_STACK.undo_last()
    assert sorted(p.name for p in desktop.iterdir()) == ["a.pdf", "b.pdf", "keep.txt"]
    assert list(documents.iterdir()) == []


def test_move_pushes_undo_before_mutating(_sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """security-and-privacy.md §8.3: the inverse is registered *before* the
    mutation, so an interrupted move is still undoable."""
    _make(_sandbox / "Desktop", "a.pdf")
    depth_at_move: list[bool] = []

    real_move = files.shutil.move

    def spy(src: str, dst: str) -> Any:
        depth_at_move.append(UNDO_STACK.can_undo())
        return real_move(src, dst)

    monkeypatch.setattr(files.shutil, "move", spy)
    files.move_files("all pdfs", "Documents", "Desktop")
    assert depth_at_move == [True]


def test_move_never_overwrites_an_existing_file(_sandbox: Path) -> None:
    desktop, documents = _sandbox / "Desktop", _sandbox / "Documents"
    _make(desktop, "report.pdf")
    (documents / "report.pdf").write_text("original", encoding="utf-8")

    files.move_files("all pdfs", "Documents", "Desktop")
    assert (documents / "report.pdf").read_text(encoding="utf-8") == "original"
    assert (documents / "report (2).pdf").exists()


def test_move_with_no_matches_reports_it(_sandbox: Path) -> None:
    assert "couldn't find any files" in files.move_files("all pdfs", "Documents", "Desktop")


def test_batch_cap_refuses_oversized_move(_sandbox: Path) -> None:
    files.configure(max_batch=3)
    _make(_sandbox / "Desktop", *[f"f{i}.pdf" for i in range(5)])
    result = files.move_files("all pdfs", "Documents", "Desktop")
    assert "more than I'll move at once" in result
    assert len(list((_sandbox / "Desktop").iterdir())) == 5


# ---------------------------------------------------------------------------
# rename_file + undo
# ---------------------------------------------------------------------------


def test_rename_file_and_undo(_sandbox: Path) -> None:
    desktop = _sandbox / "Desktop"
    _make(desktop, "budget report.xlsx")

    assert "Renamed" in files.rename_file("budget report", "budget 2026")
    assert (desktop / "budget 2026.xlsx").exists()

    UNDO_STACK.undo_last()
    assert (desktop / "budget report.xlsx").exists()
    assert not (desktop / "budget 2026.xlsx").exists()


def test_rename_keeps_extension_when_new_name_has_none(_sandbox: Path) -> None:
    _make(_sandbox / "Desktop", "notes.txt")
    files.rename_file("notes", "meeting notes")
    assert (_sandbox / "Desktop" / "meeting notes.txt").exists()


def test_rename_refuses_when_query_matches_several(_sandbox: Path) -> None:
    _make(_sandbox / "Desktop", "report a.pdf", "report b.pdf")
    result = files.rename_file("report", "final")
    assert "more than one file" in result
    assert (_sandbox / "Desktop" / "report a.pdf").exists()


def test_rename_refuses_to_clobber(_sandbox: Path) -> None:
    _make(_sandbox / "Desktop", "a.txt", "b.txt")
    assert "already a file called" in files.rename_file("a.txt", "b.txt")


# ---------------------------------------------------------------------------
# delete_files
# ---------------------------------------------------------------------------


def test_delete_files_removes_matches(_sandbox: Path) -> None:
    desktop = _sandbox / "Desktop"
    _make(desktop, "old log.log", "keep.txt")
    result = files.delete_files("old logs")
    assert "Recycle Bin" in result
    assert [p.name for p in desktop.iterdir()] == ["keep.txt"]


def test_delete_uses_recycle_bin_not_unlink(
    _sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Recycle Bin is what makes a misheard delete recoverable, and is why
    delete_files can be `confirm` rather than `blocked`. Assert the tool goes
    through that boundary rather than removing files outright."""
    _make(_sandbox / "Desktop", "a.log")
    recycled: list[list[Path]] = []
    monkeypatch.setattr(files, "_recycle", lambda paths: recycled.append(list(paths)))
    files.delete_files("all logs")
    assert len(recycled) == 1
    assert [p.name for p in recycled[0]] == ["a.log"]


def test_delete_undo_names_the_files_and_where_they_went(_sandbox: Path) -> None:
    """Undo for a delete is guided recovery, not an automatic restore — see
    files._undo_delete_files for why. It must still name what to recover."""
    _make(_sandbox / "Desktop", "a.log")
    files.delete_files("all logs")
    message = UNDO_STACK.undo_last()
    assert "a.log" in message and "Recycle Bin" in message


def test_batch_cap_refuses_oversized_delete(_sandbox: Path) -> None:
    files.configure(max_batch=3)
    _make(_sandbox / "Desktop", *[f"f{i}.log" for i in range(5)])
    result = files.delete_files("all logs")
    assert "more than I'll delete at once" in result
    assert len(list((_sandbox / "Desktop").iterdir())) == 5


def test_delete_failure_returns_string_not_raise(
    _sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make(_sandbox / "Desktop", "a.log")

    def boom(paths: Any) -> None:
        raise OSError("shell said no")

    monkeypatch.setattr(files, "_recycle", boom)
    assert "Could not delete" in files.delete_files("all logs")


# ---------------------------------------------------------------------------
# Registry contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["move_files", "rename_file", "delete_files"])
def test_mutating_file_tools_are_confirm_with_undo_and_preview(name: str) -> None:
    spec = REGISTRY.get(name)
    assert spec is not None
    assert spec.risk == "confirm", f"{name} deletes or overwrites — it must be confirm-gated"
    assert spec.tier == "local"
    assert spec.undo is not None, f"{name} mutates state and must register an inverse"
    assert spec.preview is not None, f"{name}'s effect can't be read off its arguments"


def test_find_file_is_safe_and_read_only() -> None:
    spec = REGISTRY.get("find_file")
    assert spec is not None
    assert spec.risk == "safe"
    assert spec.undo is None


def test_undo_metadata_names_real_functions() -> None:
    for name in ("move_files", "rename_file", "delete_files"):
        spec = REGISTRY.get(name)
        assert spec is not None and spec.undo is not None
        assert callable(getattr(files, spec.undo)), f"{name}.undo names a missing function"


def test_preview_describes_the_real_effect(_sandbox: Path) -> None:
    """The §8.2 requirement: the spoken prompt says what will actually happen,
    with a count and a folder — not just the tool's arguments."""
    _make(_sandbox / "Desktop", "a.pdf", "b.pdf")
    spec = REGISTRY.get("move_files")
    assert spec is not None and spec.preview is not None
    summary = spec.preview(query="all pdfs", destination="Documents", source="Desktop")
    assert "2 files" in summary and "Desktop" in summary and "Documents" in summary
