"""Tool registry and execution tests: schema generation, tier/risk enforcement,
undo registration. Phase 2.

Every Windows-API boundary (pycaw, screen_brightness_control, subprocess,
win32gui/win32process/win32com, psutil) is monkeypatched at the small wrapper
functions tools/system.py and tools/apps.py isolate it behind, per this
task's mockability requirement — nothing here touches real audio hardware,
a real display, or a real Bluetooth/Wi-Fi radio. A few tests exercise the
real (read-only) Start Menu/App Paths/process-table scan against this actual
machine, since that's safe and gives genuine signal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from munshiji.security.undo import UNDO_STACK
from munshiji.tools import apps, system
from munshiji.tools.registry import REGISTRY


@pytest.fixture(autouse=True)
def _clear_undo_stack() -> Any:
    UNDO_STACK.clear()
    yield
    UNDO_STACK.clear()


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Registry / schema / tier / risk
# ---------------------------------------------------------------------------

_SAFE_TOOLS = [
    "set_volume",
    "mute",
    "get_volume",
    "set_brightness",
    "get_brightness",
    "lock_screen",
    "sleep",
    "wifi_toggle",
    "bluetooth_toggle",
    "wifi_status",
    "bluetooth_status",
    "open_app",
    "close_app",
    "focus_app",
    "minimize_app",
    "maximize_app",
    "list_apps",
]
_CONFIRM_TOOLS = ["shutdown", "restart"]


@pytest.mark.parametrize("name", _SAFE_TOOLS)
def test_safe_tools_registered_local_safe(name: str) -> None:
    spec = REGISTRY.get(name)
    assert spec is not None, f"{name} not registered"
    assert spec.tier == "local"
    assert spec.risk == "safe"


@pytest.mark.parametrize("name", _CONFIRM_TOOLS)
def test_confirm_tools_registered_local_confirm(name: str) -> None:
    spec = REGISTRY.get(name)
    assert spec is not None, f"{name} not registered"
    assert spec.tier == "local"
    assert spec.risk == "confirm"


def test_all_19_tools_present() -> None:
    assert len(_SAFE_TOOLS) + len(_CONFIRM_TOOLS) == 19
    for name in _SAFE_TOOLS + _CONFIRM_TOOLS:
        assert name in REGISTRY


def test_confirm_tools_still_reachable_from_llm_path() -> None:
    # risk="confirm" is not risk="blocked" -- shutdown/restart stay visible
    # to the LLM tool-call path; the actual confirmation gate is Phase 3's
    # security/confirm.py, not registry exclusion.
    visible_names = {t.name for t in REGISTRY.iter_llm_visible()}
    for name in _CONFIRM_TOOLS:
        assert name in visible_names


def test_set_volume_schema_has_optional_level_and_direction() -> None:
    spec = REGISTRY.get("set_volume")
    assert spec is not None
    props = spec.schema["properties"]
    assert props["level"]["type"] == "integer"
    assert props["direction"]["type"] == "string"
    assert spec.schema["required"] == []


def test_open_app_schema_requires_app() -> None:
    spec = REGISTRY.get("open_app")
    assert spec is not None
    assert spec.schema["required"] == ["app"]


def test_minimize_app_schema_app_is_optional() -> None:
    spec = REGISTRY.get("minimize_app")
    assert spec is not None
    assert spec.schema["required"] == []


def test_undo_metadata_matches_real_inverse_function_names() -> None:
    mutating = {
        "set_volume": system._undo_set_volume,
        "mute": system._undo_mute,
        "set_brightness": system._undo_set_brightness,
        "shutdown": system._abort_shutdown,
        "restart": system._abort_shutdown,
        "wifi_toggle": system._undo_wifi_toggle,
        "bluetooth_toggle": system._undo_bluetooth_toggle,
        "open_app": apps._undo_open_app,
        "close_app": apps._undo_close_app,
        "focus_app": apps._undo_focus_app,
        "minimize_app": apps._undo_window_placement,
        "maximize_app": apps._undo_window_placement,
    }
    for name, inverse_func in mutating.items():
        spec = REGISTRY.get(name)
        assert spec is not None
        assert spec.undo == inverse_func.__name__


def test_read_only_and_no_sensible_inverse_tools_have_no_undo() -> None:
    for name in (
        "get_volume",
        "get_brightness",
        "wifi_status",
        "bluetooth_status",
        "list_apps",
        "lock_screen",
        "sleep",
    ):
        spec = REGISTRY.get(name)
        assert spec is not None
        assert spec.undo is None


# ---------------------------------------------------------------------------
# system.py -- volume
# ---------------------------------------------------------------------------


class _FakeVolumeState:
    def __init__(self, pct: int = 50, muted: bool = False) -> None:
        self.pct = pct
        self.muted = muted


def _patch_volume(monkeypatch: pytest.MonkeyPatch, state: _FakeVolumeState) -> None:
    monkeypatch.setattr(system, "_get_volume_pct", lambda: state.pct)
    monkeypatch.setattr(system, "_set_volume_pct", lambda pct: setattr(state, "pct", pct))
    monkeypatch.setattr(system, "_get_mute_state", lambda: state.muted)
    monkeypatch.setattr(system, "_set_mute_state", lambda flag: setattr(state, "muted", flag))


def test_set_volume_absolute_level_and_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeVolumeState(pct=50)
    _patch_volume(monkeypatch, state)
    result = system.set_volume(level=80)
    assert result == "Volume set to 80%."
    assert state.pct == 80
    undo_msg = UNDO_STACK.undo_last()
    assert state.pct == 50
    assert "50%" in undo_msg


def test_set_volume_relative_direction(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeVolumeState(pct=50)
    _patch_volume(monkeypatch, state)
    system.set_volume(direction="up")
    assert state.pct == 60
    system.set_volume(direction="down")
    assert state.pct == 50


def test_set_volume_clamps_to_0_100(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeVolumeState(pct=95)
    _patch_volume(monkeypatch, state)
    system.set_volume(direction="up")
    assert state.pct == 100


def test_set_volume_no_args_rejected() -> None:
    assert "Specify either" in system.set_volume()


def test_set_volume_out_of_range_level_rejected() -> None:
    assert "between 0 and 100" in system.set_volume(level=150)


def test_set_volume_bad_direction_rejected() -> None:
    assert "'up' or 'down'" in system.set_volume(direction="sideways")


def test_set_volume_validation_failure_does_not_touch_undo_stack() -> None:
    system.set_volume()
    assert not UNDO_STACK.can_undo()


def test_set_volume_pushes_undo_before_mutating(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_get_volume_pct", lambda: 40)

    def boom(pct: int) -> None:
        raise RuntimeError("simulated hardware failure")

    monkeypatch.setattr(system, "_set_volume_pct", boom)
    result = system.set_volume(level=80)
    assert "Could not change volume" in result
    # The undo record was pushed before _set_volume_pct was called, per
    # security-and-privacy.md -- it's on the stack even though the mutation
    # itself failed.
    assert UNDO_STACK.can_undo()


def test_get_volume_reports_level_and_mute(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeVolumeState(pct=42, muted=True)
    _patch_volume(monkeypatch, state)
    assert system.get_volume() == "Volume is 42% (muted)."


def test_get_volume_error_path_returns_string_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> int:
        raise RuntimeError("no audio device")

    monkeypatch.setattr(system, "_get_volume_pct", boom)
    result = system.get_volume()
    assert isinstance(result, str)
    assert "Could not read volume" in result


def test_mute_toggle_when_no_state_given(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeVolumeState(muted=False)
    _patch_volume(monkeypatch, state)
    result = system.mute()
    assert result == "Audio muted."
    assert state.muted is True
    UNDO_STACK.undo_last()
    assert state.muted is False


def test_mute_explicit_state(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeVolumeState(muted=False)
    _patch_volume(monkeypatch, state)
    system.mute(state="on")
    assert state.muted is True
    system.mute(state="off")
    assert state.muted is False


def test_mute_bad_state_rejected() -> None:
    assert "'on', 'off'" in system.mute(state="bogus")


# ---------------------------------------------------------------------------
# system.py -- brightness
# ---------------------------------------------------------------------------


class _FakeBrightnessState:
    def __init__(self, pct: int = 50) -> None:
        self.pct = pct


def _patch_brightness(monkeypatch: pytest.MonkeyPatch, state: _FakeBrightnessState) -> None:
    monkeypatch.setattr(system, "_get_brightness_pct", lambda: state.pct)
    monkeypatch.setattr(system, "_set_brightness_pct", lambda pct: setattr(state, "pct", pct))


def test_set_brightness_absolute_and_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeBrightnessState(pct=30)
    _patch_brightness(monkeypatch, state)
    result = system.set_brightness(level=70)
    assert result == "Brightness set to 70%."
    assert state.pct == 70
    UNDO_STACK.undo_last()
    assert state.pct == 30


def test_set_brightness_relative_direction(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeBrightnessState(pct=50)
    _patch_brightness(monkeypatch, state)
    system.set_brightness(direction="down")
    assert state.pct == 40


def test_get_brightness_reports_level(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _FakeBrightnessState(pct=88)
    _patch_brightness(monkeypatch, state)
    assert system.get_brightness() == "Brightness is 88%."


def test_set_brightness_bad_level_rejected() -> None:
    assert "between 0 and 100" in system.set_brightness(level=-5)


def test_get_brightness_error_path_returns_string(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> int:
        raise RuntimeError("no controllable display")

    monkeypatch.setattr(system, "_get_brightness_pct", boom)
    assert "Could not read brightness" in system.get_brightness()


# ---------------------------------------------------------------------------
# system.py -- power
# ---------------------------------------------------------------------------


def test_lock_screen_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_lock_workstation", lambda: None)
    assert system.lock_screen() == "Screen locked."


def test_lock_screen_failure_returns_string_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise OSError("denied")

    monkeypatch.setattr(system, "_lock_workstation", boom)
    result = system.lock_screen()
    assert isinstance(result, str)
    assert "Could not lock the screen" in result


def test_sleep_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_sleep_now", lambda: None)
    assert system.sleep() == "Going to sleep."


def test_sleep_failure_returns_string(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise OSError("denied")

    monkeypatch.setattr(system, "_sleep_now", boom)
    assert "Could not put the computer to sleep" in system.sleep()


def test_shutdown_schedules_and_registers_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        system, "_run_subprocess", lambda args: (calls.append(args), _completed(0))[1]
    )
    result = system.shutdown(delay_s=15)
    assert "Shutting down in 15 seconds" in result
    assert calls[0] == ["shutdown", "/s", "/t", "15"]
    assert UNDO_STACK.can_undo()

    undo_calls: list[list[str]] = []
    monkeypatch.setattr(
        system, "_run_subprocess", lambda args: (undo_calls.append(args), _completed(0))[1]
    )
    undo_msg = UNDO_STACK.undo_last()
    assert undo_calls[0] == ["shutdown", "/a"]
    assert "cancelled" in undo_msg.lower()


def test_shutdown_negative_delay_rejected() -> None:
    assert "delay_s" in system.shutdown(delay_s=-1)
    assert not UNDO_STACK.can_undo()


def test_shutdown_subprocess_failure_returns_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system, "_run_subprocess", lambda args: _completed(1, stderr="access denied")
    )
    result = system.shutdown()
    assert "Could not schedule shutdown" in result


def test_restart_schedules_and_shares_abort_inverse(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        system, "_run_subprocess", lambda args: (calls.append(args), _completed(0))[1]
    )
    result = system.restart(delay_s=5)
    assert "Restarting in 5 seconds" in result
    assert calls[0] == ["shutdown", "/r", "/t", "5"]
    spec = REGISTRY.get("restart")
    assert spec is not None
    assert spec.undo == "_abort_shutdown"


# ---------------------------------------------------------------------------
# system.py -- Wi-Fi
# ---------------------------------------------------------------------------

_NETSH_TABLE = (
    "Admin State    State          Type             Interface Name\n"
    "-------------------------------------------------------------------\n"
    "Enabled        Connected      Dedicated        Wi-Fi\n"
    "Enabled        Connected      Dedicated        Ethernet\n"
)


def test_find_wifi_interface_parses_netsh_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_run_subprocess", lambda args: _completed(0, stdout=_NETSH_TABLE))
    iface = system._find_wifi_interface()
    assert iface is not None
    assert iface["name"] == "Wi-Fi"
    assert iface["admin_state"] == "Enabled"


def test_find_wifi_interface_none_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    table = (
        "Admin State    State          Type             Interface Name\n"
        "-------------------------------------------------------------------\n"
        "Enabled        Connected      Dedicated        Ethernet\n"
    )
    monkeypatch.setattr(system, "_run_subprocess", lambda args: _completed(0, stdout=table))
    assert system._find_wifi_interface() is None


def test_wifi_toggle_on_and_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_get_wifi_enabled", lambda: False)
    set_calls: list[bool] = []
    monkeypatch.setattr(system, "_set_wifi_enabled", lambda flag: set_calls.append(flag))
    result = system.wifi_toggle("on")
    assert result == "Wi-Fi turned on."
    assert set_calls == [True]
    UNDO_STACK.undo_last()
    assert set_calls == [True, False]


def test_wifi_toggle_bad_state_rejected() -> None:
    assert "'on' or 'off'" in system.wifi_toggle("sideways")
    assert not UNDO_STACK.can_undo()


def test_wifi_status_reports_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_get_wifi_enabled", lambda: True)
    assert system.wifi_status() == "Wi-Fi is on."


def test_wifi_status_no_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_get_wifi_enabled", lambda: None)
    assert system.wifi_status() == "No Wi-Fi adapter found."


# ---------------------------------------------------------------------------
# system.py -- Bluetooth
# ---------------------------------------------------------------------------


def test_bluetooth_toggle_off_and_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_get_bluetooth_enabled", lambda: True)
    set_calls: list[bool] = []
    monkeypatch.setattr(system, "_set_bluetooth_enabled", lambda flag: set_calls.append(flag))
    result = system.bluetooth_toggle("off")
    assert result == "Bluetooth turned off."
    assert set_calls == [False]
    UNDO_STACK.undo_last()
    assert set_calls == [False, True]


def test_bluetooth_toggle_bad_state_rejected() -> None:
    assert "'on' or 'off'" in system.bluetooth_toggle("bogus")


def test_bluetooth_status_reports_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_get_bluetooth_enabled", lambda: False)
    assert system.bluetooth_status() == "Bluetooth is off."


def test_bluetooth_status_no_radio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_get_bluetooth_enabled", lambda: None)
    assert system.bluetooth_status() == "No Bluetooth radio found."


def test_bluetooth_radio_instance_id_parses_powershell_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        system, "_run_subprocess", lambda args: _completed(0, stdout="USB\\VID_1234\\RADIO\r\n")
    )
    assert system._bluetooth_radio_instance_id() == "USB\\VID_1234\\RADIO"


def test_bluetooth_radio_instance_id_none_when_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_run_subprocess", lambda args: _completed(0, stdout=""))
    assert system._bluetooth_radio_instance_id() is None


def test_set_bluetooth_enabled_raises_when_no_radio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_bluetooth_radio_instance_id", lambda: None)
    with pytest.raises(RuntimeError, match="No Bluetooth radio"):
        system._set_bluetooth_enabled(True)


# ---------------------------------------------------------------------------
# apps.py -- installed-app index / fuzzy matching
# ---------------------------------------------------------------------------


def test_scan_start_menu_finds_lnk_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    start_menu = tmp_path / "Start Menu" / "Programs"
    sub = start_menu / "Accessories"
    sub.mkdir(parents=True)
    (start_menu / "Notepad.lnk").write_bytes(b"")
    (sub / "Calculator.lnk").write_bytes(b"")
    monkeypatch.setattr(apps, "_START_MENU_DIRS", [start_menu])
    index = apps._scan_start_menu()
    assert index["Notepad"] == str(start_menu / "Notepad.lnk")
    assert index["Calculator"] == str(sub / "Calculator.lnk")


def test_scan_start_menu_missing_dir_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(apps, "_START_MENU_DIRS", [tmp_path / "does-not-exist"])
    assert apps._scan_start_menu() == {}


def test_build_app_index_against_real_machine_does_not_raise() -> None:
    index = apps.build_app_index()
    assert isinstance(index, dict)


def test_running_processes_against_real_machine_does_not_raise() -> None:
    procs = apps._running_processes()
    assert isinstance(procs, dict)


def test_resolve_installed_app_recovers_asr_typo(monkeypatch: pytest.MonkeyPatch) -> None:
    # "chrome" against "Google Chrome" scores ~82 with rapidfuzz's default
    # WRatio scorer -- comfortably above the 75 cutoff, the kind of partial/
    # reordered match ASR mangling produces.
    monkeypatch.setattr(
        apps, "build_app_index", lambda: {"Google Chrome": "chrome.exe", "Notepad": "notepad.exe"}
    )
    resolved = apps.resolve_installed_app("chrome")
    assert resolved is not None
    name, target = resolved
    assert name == "Google Chrome"
    assert target == "chrome.exe"


def test_resolve_installed_app_below_cutoff_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "build_app_index", lambda: {"Chrome": "chrome.exe"})
    assert apps.resolve_installed_app("completely unrelated program name") is None


def test_resolve_installed_app_empty_index_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "build_app_index", lambda: {})
    assert apps.resolve_installed_app("anything") is None


class _FakeProcess:
    def __init__(self, pid: int, name: str = "proc.exe") -> None:
        self.pid = pid
        self._name = name
        self.terminated = False

    def name(self) -> str:
        return self._name

    def terminate(self) -> None:
        self.terminated = True


def test_resolve_running_app_recovers_asr_typo(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProcess(pid=101, name="chrome.exe")
    monkeypatch.setattr(apps, "_running_processes", lambda: {"chrome": fake})
    resolved = apps.resolve_running_app("chrom")
    assert resolved is not None
    name, proc = resolved
    assert name == "chrome"
    assert proc is fake


def test_resolve_running_app_none_when_nothing_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "_running_processes", lambda: {})
    assert apps.resolve_running_app("chrome") is None


# ---------------------------------------------------------------------------
# apps.py -- open_app / close_app
# ---------------------------------------------------------------------------


def test_open_app_requires_name() -> None:
    assert "Specify which app to open" in apps.open_app("")


def test_open_app_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "resolve_installed_app", lambda q: None)
    assert "Could not find an app matching" in apps.open_app("nonexistent")


def test_open_app_launches_and_undo_terminates_by_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "resolve_installed_app", lambda q: ("Chrome", "chrome.exe"))
    monkeypatch.setattr(apps, "_launch", lambda target: 4242)
    result = apps.open_app("chrom")
    assert result == "Opening Chrome."
    assert UNDO_STACK.can_undo()

    terminated: list[int] = []
    monkeypatch.setattr(apps, "_terminate_pid", lambda pid: terminated.append(pid))
    undo_msg = UNDO_STACK.undo_last()
    assert terminated == [4242]
    assert "Closed Chrome" in undo_msg


def test_open_app_launch_failure_leaves_nothing_to_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "resolve_installed_app", lambda q: ("Chrome", "chrome.exe"))

    def boom(target: str) -> int:
        raise RuntimeError("ShellExecuteEx failed")

    monkeypatch.setattr(apps, "_launch", boom)
    result = apps.open_app("chrome")
    assert "Could not open" in result
    assert not UNDO_STACK.can_undo()


def test_close_app_requires_name() -> None:
    assert "Specify which app to close" in apps.close_app("")


def test_close_app_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "resolve_running_app", lambda q: None)
    assert "does not appear to be running" in apps.close_app("ghost")


def test_close_app_terminates_and_pushes_undo_before_terminating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeProcess(pid=5, name="notepad.exe")

    def boom() -> None:
        raise RuntimeError("access denied")

    fake.terminate = boom  # type: ignore[method-assign]
    monkeypatch.setattr(apps, "resolve_running_app", lambda q: ("notepad", fake))
    result = apps.close_app("notepad")
    assert "Could not close" in result
    # Undo was registered before terminate() was attempted, even though the
    # (simulated) termination itself failed.
    assert UNDO_STACK.can_undo()


def test_close_app_success_and_undo_reopens_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProcess(pid=6, name="notepad.exe")
    monkeypatch.setattr(apps, "resolve_running_app", lambda q: ("notepad", fake))
    result = apps.close_app("notepad")
    assert result == "Closed notepad."
    assert fake.terminated is True

    reopened: list[str] = []
    monkeypatch.setattr(
        apps, "open_app", lambda name: (reopened.append(name), "Opening notepad.")[1]
    )
    undo_msg = UNDO_STACK.undo_last()
    assert reopened == ["notepad"]
    assert undo_msg == "Opening notepad."


# ---------------------------------------------------------------------------
# apps.py -- focus_app / minimize_app / maximize_app
# ---------------------------------------------------------------------------


def test_focus_app_switches_and_undo_restores_previous(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProcess(pid=7, name="chrome.exe")
    monkeypatch.setattr(apps, "resolve_running_app", lambda q: ("chrome", fake))
    monkeypatch.setattr(apps, "_windows_for_pid", lambda pid: [999])
    monkeypatch.setattr(apps, "_foreground_window", lambda: 111)
    focused: list[int] = []
    monkeypatch.setattr(apps, "_set_foreground", lambda hwnd: focused.append(hwnd))
    result = apps.focus_app("chrome")
    assert result == "Switched to chrome."
    assert focused == [999]

    monkeypatch.setattr(apps, "_window_exists", lambda hwnd: True)
    undo_msg = UNDO_STACK.undo_last()
    assert focused == [999, 111]
    assert "Restored" in undo_msg


def test_focus_app_no_visible_window(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProcess(pid=8, name="ghost.exe")
    monkeypatch.setattr(apps, "resolve_running_app", lambda q: ("ghost", fake))
    monkeypatch.setattr(apps, "_windows_for_pid", lambda pid: [])
    result = apps.focus_app("ghost")
    assert "no visible window to focus" in result
    assert not UNDO_STACK.can_undo()


def test_focus_app_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "resolve_running_app", lambda q: None)
    assert "does not appear to be running" in apps.focus_app("ghost")


def test_focus_app_requires_name() -> None:
    assert "Specify which app to focus" in apps.focus_app("")


def test_minimize_app_named_and_undo_restores_placement(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProcess(pid=9, name="notepad.exe")
    monkeypatch.setattr(apps, "resolve_running_app", lambda q: ("notepad", fake))
    monkeypatch.setattr(apps, "_windows_for_pid", lambda pid: [55])
    monkeypatch.setattr(apps, "_window_placement", lambda hwnd: "PLACEMENT-55")
    minimized: list[int] = []
    monkeypatch.setattr(apps, "_minimize", lambda hwnd: minimized.append(hwnd))
    result = apps.minimize_app("notepad")
    assert result == "Minimized notepad."
    assert minimized == [55]

    restored: list[tuple[int, str]] = []
    monkeypatch.setattr(apps, "_window_exists", lambda hwnd: True)
    monkeypatch.setattr(
        apps, "_restore_placement", lambda hwnd, placement: restored.append((hwnd, placement))
    )
    undo_msg = UNDO_STACK.undo_last()
    assert restored == [(55, "PLACEMENT-55")]
    assert "restored" in undo_msg.lower()


def test_minimize_app_current_window_when_none_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "_foreground_window", lambda: 77)
    monkeypatch.setattr(apps, "_window_title", lambda hwnd: "Untitled - Notepad")
    monkeypatch.setattr(apps, "_window_placement", lambda hwnd: "PLACEMENT-77")
    minimized: list[int] = []
    monkeypatch.setattr(apps, "_minimize", lambda hwnd: minimized.append(hwnd))
    result = apps.minimize_app()
    assert result == "Minimized Untitled - Notepad."
    assert minimized == [77]


def test_minimize_app_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "resolve_running_app", lambda q: None)
    assert "Could not find a window for 'xyz'" in apps.minimize_app("xyz")


def test_minimize_app_no_current_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "_foreground_window", lambda: 0)
    assert apps.minimize_app() == "No window is currently focused."


def test_maximize_app_shares_placement_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProcess(pid=10, name="calc.exe")
    monkeypatch.setattr(apps, "resolve_running_app", lambda q: ("calc", fake))
    monkeypatch.setattr(apps, "_windows_for_pid", lambda pid: [88])
    monkeypatch.setattr(apps, "_window_placement", lambda hwnd: "PLACEMENT-88")
    monkeypatch.setattr(apps, "_maximize", lambda hwnd: None)
    result = apps.maximize_app("calc")
    assert result == "Maximized calc."
    spec = REGISTRY.get("maximize_app")
    assert spec is not None
    assert spec.undo == "_undo_window_placement"


# ---------------------------------------------------------------------------
# apps.py -- list_apps
# ---------------------------------------------------------------------------


class _FakeWin32Gui:
    def __init__(self, windows: dict[int, tuple[bool, str]]) -> None:
        self._windows = windows

    def EnumWindows(self, callback: Any, extra: Any) -> None:
        for hwnd in list(self._windows):
            callback(hwnd, extra)

    def IsWindowVisible(self, hwnd: int) -> bool:
        return self._windows[hwnd][0]

    def GetWindowText(self, hwnd: int) -> str:
        return self._windows[hwnd][1]


class _FakeWin32Process:
    def __init__(self, pid_by_hwnd: dict[int, int]) -> None:
        self._pid_by_hwnd = pid_by_hwnd

    def GetWindowThreadProcessId(self, hwnd: int) -> tuple[int, int]:
        return (0, self._pid_by_hwnd[hwnd])


def test_list_apps_lists_visible_named_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    windows = {1: (True, "Untitled - Notepad"), 2: (False, "Hidden"), 3: (True, "Calculator")}
    pid_by_hwnd = {1: 101, 2: 102, 3: 103}
    monkeypatch.setattr(apps, "win32gui", _FakeWin32Gui(windows))
    monkeypatch.setattr(apps, "win32process", _FakeWin32Process(pid_by_hwnd))
    names = {101: "notepad.exe", 103: "calculator.exe"}
    monkeypatch.setattr(apps.psutil, "Process", lambda pid: _FakeProcess(pid, names[pid]))
    result = apps.list_apps()
    assert result == "Running: calculator.exe, notepad.exe"


def test_list_apps_none_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apps, "win32gui", _FakeWin32Gui({}))
    result = apps.list_apps()
    assert result == "No visible applications are currently running."


def test_list_apps_error_path_returns_string_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Boom:
        def EnumWindows(self, *_args: Any) -> None:
            raise RuntimeError("EnumWindows failed")

    monkeypatch.setattr(apps, "win32gui", _Boom())
    result = apps.list_apps()
    assert isinstance(result, str)
    assert "Could not list running apps" in result
