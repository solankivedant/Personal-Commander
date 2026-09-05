"""Launch, focus, minimize, close applications via the Start Menu / App Paths
index. Tier 1. Phase 2."""

from __future__ import annotations

import os
import winreg
from pathlib import Path
from typing import Any

import psutil
import win32con  # type: ignore[import-untyped]
import win32gui  # type: ignore[import-untyped]
import win32process  # type: ignore[import-untyped]
from rapidfuzz import process as fuzz_process
from win32com.shell import shell, shellcon  # type: ignore[import-untyped]

from munshiji.security.undo import UNDO_STACK
from munshiji.tools.registry import tool

# rapidfuzz.process.extractOne score cutoff below which we treat a spoken/
# typed app name as unresolved rather than guessing wrong. Mirrors
# config/default.yaml's `tools.fuzzy_app_cutoff` — call configure() at
# bootstrap to sync it (see tools/system.py's configure() for the same
# pattern); this value is just the fallback default.
_FUZZY_CUTOFF = 75


def configure(*, fuzzy_cutoff: int | None = None) -> None:
    """Sync this module's tunables from `config.tools` at bootstrap."""
    global _FUZZY_CUTOFF
    if fuzzy_cutoff is not None:
        _FUZZY_CUTOFF = fuzzy_cutoff

_START_MENU_SUBPATH = "Microsoft/Windows/Start Menu/Programs"
_START_MENU_DIRS = [
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / _START_MENU_SUBPATH,
    Path(os.environ.get("APPDATA", "")) / _START_MENU_SUBPATH,
]

_APP_PATHS_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
]


# ---------------------------------------------------------------------------
# Shared app-name index + fuzzy resolution. Every tool below (open/close/
# focus/minimize/maximize) resolves through one of these two functions rather
# than re-scanning the Start Menu / registry / process table itself.
# ---------------------------------------------------------------------------


def _scan_start_menu() -> dict[str, str]:
    """Start Menu .lnk shortcuts (both the all-users and per-user Programs
    folders) -> shortcut path, keyed by the shortcut's display name."""
    apps: dict[str, str] = {}
    for base in _START_MENU_DIRS:
        try:
            if not str(base) or not base.exists():
                continue
            for lnk in base.rglob("*.lnk"):
                apps.setdefault(lnk.stem, str(lnk))
        except OSError:
            continue
    return apps


def _scan_app_paths() -> dict[str, str]:
    """Registered `App Paths` registry entries -> resolved executable path.
    This is what Windows itself uses to resolve a bare exe name typed into
    the Run box, and it catches apps that don't ship a Start Menu shortcut."""
    apps: dict[str, str] = {}
    for hive, subkey in _APP_PATHS_KEYS:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                count = winreg.QueryInfoKey(key)[0]
                for i in range(count):
                    try:
                        name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, name) as app_key:
                            path, _ = winreg.QueryValueEx(app_key, "")
                            apps.setdefault(Path(name).stem, path)
                    except OSError:
                        continue
        except OSError:
            continue
    return apps


def build_app_index() -> dict[str, str]:
    """Installed-application name -> launch target, combining registered
    App Paths and Start Menu shortcuts. Rebuilt on every call rather than
    cached at import time — installing/uninstalling an app shouldn't require
    restarting the assistant, and scanning a few hundred filesystem/registry
    entries is fast relative to voice-loop latency budgets."""
    index = _scan_app_paths()
    index.update(_scan_start_menu())
    return index


def resolve_installed_app(query: str) -> tuple[str, str] | None:
    """Fuzzy-resolve a spoken/typed app name against the installed-app index.
    Returns (matched_name, launch_target), or None below the match cutoff —
    this is what recovers ASR mangling like "chrom" -> "Chrome"."""
    index = build_app_index()
    if not index:
        return None
    match = fuzz_process.extractOne(query, list(index.keys()), score_cutoff=_FUZZY_CUTOFF)
    if match is None:
        return None
    name = match[0]
    return name, index[name]


def _running_processes() -> dict[str, psutil.Process]:
    """Currently running processes keyed by their executable's stem name, for
    fuzzy-matching close/focus/minimize/maximize against what's actually
    open rather than what's installed."""
    procs: dict[str, psutil.Process] = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info["name"]
            if not name:
                continue
            procs.setdefault(Path(name).stem, proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return procs


def resolve_running_app(query: str) -> tuple[str, psutil.Process] | None:
    """Fuzzy-resolve a spoken/typed app name against currently running
    processes. Returns (matched_name, psutil.Process), or None below cutoff
    or if nothing matching is running."""
    procs = _running_processes()
    if not procs:
        return None
    match = fuzz_process.extractOne(query, list(procs.keys()), score_cutoff=_FUZZY_CUTOFF)
    if match is None:
        return None
    name = match[0]
    return name, procs[name]


# ---------------------------------------------------------------------------
# Windows API boundary for launching and window control. Isolated in small
# functions so tests can monkeypatch them without a real desktop session.
# ---------------------------------------------------------------------------


def _launch(target: str) -> int:
    """Launch `target` (an .exe path, an App-Paths command, or a .lnk
    shortcut) via ShellExecuteEx, returning the PID of the spawned process.

    ShellExecuteEx rather than subprocess.Popen: Popen can't execute .lnk
    shortcuts directly, and wrapping in `cmd /c start` returns cmd's PID —
    cmd exits immediately once it hands off, so that PID can't be used to
    terminate the actual app later for undo. ShellExecuteEx with
    SEE_MASK_NOCLOSEPROCESS hands back a real process handle for exactly
    this reason.
    """
    info = shell.ShellExecuteEx(
        nShow=win32con.SW_SHOWNORMAL,
        fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
        lpVerb="open",
        lpFile=target,
    )
    handle = info["hProcess"]
    return int(win32process.GetProcessId(handle))


def _terminate_pid(pid: int) -> None:
    psutil.Process(pid).terminate()


def _windows_for_pid(pid: int) -> list[int]:
    """Visible, titled top-level windows belonging to `pid`."""
    hwnds: list[int] = []

    def _callback(hwnd: int, _extra: None) -> bool:
        if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
            return True
        _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
        if found_pid == pid:
            hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(_callback, None)
    return hwnds


def _foreground_window() -> int:
    return int(win32gui.GetForegroundWindow())


def _set_foreground(hwnd: int) -> None:
    win32gui.SetForegroundWindow(hwnd)


def _window_placement(hwnd: int) -> Any:
    return win32gui.GetWindowPlacement(hwnd)


def _restore_placement(hwnd: int, placement: Any) -> None:
    win32gui.SetWindowPlacement(hwnd, placement)


def _minimize(hwnd: int) -> None:
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


def _maximize(hwnd: int) -> None:
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)


def _window_exists(hwnd: int) -> bool:
    return bool(hwnd) and bool(win32gui.IsWindow(hwnd))


def _window_title(hwnd: int) -> str:
    return str(win32gui.GetWindowText(hwnd))


def _resolve_target_hwnd(app: str | None) -> tuple[str, int] | None:
    """Resolve either the named app's window, or — when `app` is None — the
    current foreground window. Returns (label, hwnd) or None if nothing
    could be resolved."""
    if app is None or not app.strip():
        hwnd = _foreground_window()
        if not hwnd:
            return None
        return (_window_title(hwnd) or "the current window", hwnd)
    resolved = resolve_running_app(app.strip())
    if resolved is None:
        return None
    name, proc = resolved
    hwnds = _windows_for_pid(proc.pid)
    if not hwnds:
        return None
    return name, hwnds[0]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(tier="local", risk="safe", tags=["apps"], undo="_undo_open_app")
def open_app(app: str) -> str:
    """Launch an installed application, fuzzy-matching the spoken/typed name
    against the Start Menu and registered App Paths index.

    Args:
        app: The application name to launch, e.g. "chrome" or "notepad".
    """
    if not app or not app.strip():
        return "Specify which app to open."
    try:
        resolved = resolve_installed_app(app.strip())
        if resolved is None:
            return f"Could not find an app matching '{app}'."
        name, target = resolved
        # Undo push happens *after* _launch() here, not before, as an
        # intentional exception to the usual "push before mutate" order:
        # the inverse (terminate by PID) needs the PID that only exists once
        # the process has actually been created — there's no "previous
        # state" to capture ahead of a creation. If _launch() itself raises,
        # nothing was pushed and nothing (launched) needs undoing.
        pid = _launch(target)
        UNDO_STACK.push("open_app", f"Close {name}", lambda: _undo_open_app(pid, name))
        return f"Opening {name}."
    except Exception as exc:
        return f"Could not open '{app}': {exc}"


def _undo_open_app(pid: int, name: str) -> str:
    try:
        _terminate_pid(pid)
        return f"Closed {name}."
    except Exception as exc:
        return f"Could not undo opening {name}: {exc}"


@tool(tier="local", risk="safe", tags=["apps"], undo="_undo_close_app")
def close_app(app: str) -> str:
    """Close a currently running application, fuzzy-matching the spoken/
    typed name against running processes.

    Args:
        app: The application name to close, e.g. "chrome" or "notepad".
    """
    if not app or not app.strip():
        return "Specify which app to close."
    try:
        resolved = resolve_running_app(app.strip())
        if resolved is None:
            return f"'{app}' does not appear to be running."
        name, proc = resolved
        # Best-effort inverse: relaunching does not restore whatever
        # documents/tabs/in-app state the closed instance had — a true
        # inverse of "close" isn't representable, so this is deliberately a
        # weaker guarantee than the other undos in this module.
        UNDO_STACK.push(
            "close_app",
            f"Reopen {name} (best effort — won't restore its prior window state)",
            lambda: _undo_close_app(name),
        )
        proc.terminate()
        return f"Closed {name}."
    except Exception as exc:
        return f"Could not close '{app}': {exc}"


def _undo_close_app(name: str) -> str:
    return open_app(name)


@tool(tier="local", risk="safe", tags=["apps"], undo="_undo_focus_app")
def focus_app(app: str) -> str:
    """Bring a running application's window to the foreground.

    Args:
        app: The application name to focus, e.g. "chrome" or "notepad".
    """
    if not app or not app.strip():
        return "Specify which app to focus."
    try:
        resolved = resolve_running_app(app.strip())
        if resolved is None:
            return f"'{app}' does not appear to be running."
        name, proc = resolved
        hwnds = _windows_for_pid(proc.pid)
        if not hwnds:
            return f"Found {name} running, but it has no visible window to focus."
        previous_hwnd = _foreground_window()
        UNDO_STACK.push(
            "focus_app", "Refocus the previous window", lambda: _undo_focus_app(previous_hwnd)
        )
        _set_foreground(hwnds[0])
        return f"Switched to {name}."
    except Exception as exc:
        return f"Could not focus '{app}': {exc}"


def _undo_focus_app(hwnd: int) -> str:
    try:
        if _window_exists(hwnd):
            _set_foreground(hwnd)
            return "Restored previous window focus."
        return "The previously focused window is no longer available."
    except Exception as exc:
        return f"Could not undo focus change: {exc}"


@tool(tier="local", risk="safe", tags=["apps"], undo="_undo_window_placement")
def minimize_app(app: str | None = None) -> str:
    """Minimize an application's window, or the current foreground window if
    none is named.

    Args:
        app: The application to minimize; omit for the current window.
    """
    try:
        target = _resolve_target_hwnd(app)
        if target is None:
            if app:
                return f"Could not find a window for '{app}'."
            return "No window is currently focused."
        name, hwnd = target
        placement = _window_placement(hwnd)
        UNDO_STACK.push(
            "minimize_app",
            f"Restore {name}'s window",
            lambda: _undo_window_placement(hwnd, placement),
        )
        _minimize(hwnd)
        return f"Minimized {name}."
    except Exception as exc:
        return f"Could not minimize '{app}': {exc}"


@tool(tier="local", risk="safe", tags=["apps"], undo="_undo_window_placement")
def maximize_app(app: str | None = None) -> str:
    """Maximize an application's window, or the current foreground window if
    none is named.

    Args:
        app: The application to maximize; omit for the current window.
    """
    try:
        target = _resolve_target_hwnd(app)
        if target is None:
            if app:
                return f"Could not find a window for '{app}'."
            return "No window is currently focused."
        name, hwnd = target
        placement = _window_placement(hwnd)
        UNDO_STACK.push(
            "maximize_app",
            f"Restore {name}'s window",
            lambda: _undo_window_placement(hwnd, placement),
        )
        _maximize(hwnd)
        return f"Maximized {name}."
    except Exception as exc:
        return f"Could not maximize '{app}': {exc}"


def _undo_window_placement(hwnd: int, placement: Any) -> str:
    """Shared inverse for minimize_app() and maximize_app(): restores
    whatever placement (position, show-state — not necessarily
    maximized/minimized/normal) the window had before the mutating call."""
    try:
        if not _window_exists(hwnd):
            return "That window no longer exists."
        _restore_placement(hwnd, placement)
        return "Window restored to its previous state."
    except Exception as exc:
        return f"Could not undo window change: {exc}"


@tool(tier="local", risk="safe", tags=["apps"])
def list_apps() -> str:
    """List currently running, user-visible applications."""
    try:
        names: set[str] = set()

        def _callback(hwnd: int, _extra: None) -> bool:
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    names.add(psutil.Process(pid).name())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return True

        win32gui.EnumWindows(_callback, None)
        if not names:
            return "No visible applications are currently running."
        return "Running: " + ", ".join(sorted(names))
    except Exception as exc:
        return f"Could not list running apps: {exc}"
