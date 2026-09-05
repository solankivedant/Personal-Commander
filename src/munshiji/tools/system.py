"""Volume, mute, brightness, power, Wi-Fi/Bluetooth toggles. Tier 0. Phase 2.

Also hosts the Phase 3 undo commands (undo_last, what_can_i_undo) — see the
note above them for why they live here rather than in their own module."""

from __future__ import annotations

import ctypes
import subprocess
from ctypes import POINTER, cast
from typing import Any

from munshiji.security.undo import UNDO_STACK
from munshiji.tools.registry import tool

# Nudge size for relative volume/brightness changes ("make it louder" with no
# explicit level) and the timeout on every subprocess call this module makes.
# These mirror config/default.yaml's `tools:` section (the actual source of
# truth per engineering-standards.md's "no behaviour constants in source") —
# call configure() at bootstrap with the loaded config to sync them; the
# values below are just the fallback used if configure() is never called
# (e.g. in unit tests that import this module directly).
_VOLUME_STEP_PCT = 10
_BRIGHTNESS_STEP_PCT = 10
_SUBPROCESS_TIMEOUT_S = 10


def configure(
    *, volume_step_pct: int | None = None, brightness_step_pct: int | None = None,
    subprocess_timeout_s: int | None = None,
) -> None:
    """Sync this module's tunables from `config.tools` at bootstrap
    (see __main__.py). Call once before the FSM starts routing to tools."""
    global _VOLUME_STEP_PCT, _BRIGHTNESS_STEP_PCT, _SUBPROCESS_TIMEOUT_S
    if volume_step_pct is not None:
        _VOLUME_STEP_PCT = volume_step_pct
    if brightness_step_pct is not None:
        _BRIGHTNESS_STEP_PCT = brightness_step_pct
    if subprocess_timeout_s is not None:
        _SUBPROCESS_TIMEOUT_S = subprocess_timeout_s


# ---------------------------------------------------------------------------
# Windows API boundary. Every real OS/COM/subprocess call this module makes
# is isolated in one of the small functions below so tests can monkeypatch
# the boundary instead of requiring real speakers/displays/radios.
# ---------------------------------------------------------------------------


def _volume_interface() -> Any:
    """Live IAudioEndpointVolume COM interface for the default playback
    device. Constructed fresh on every call — pycaw/comtypes COM pointers
    aren't meant to be cached across calls from different threads."""
    from comtypes import CLSCTX_ALL  # type: ignore[import-untyped]
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore[import-untyped]

    devices = AudioUtilities.GetSpeakers()
    raw = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(raw, POINTER(IAudioEndpointVolume))


def _get_volume_pct() -> int:
    return int(round(_volume_interface().GetMasterVolumeLevelScalar() * 100))


def _set_volume_pct(pct: int) -> None:
    _volume_interface().SetMasterVolumeLevelScalar(pct / 100.0, None)


def _get_mute_state() -> bool:
    return bool(_volume_interface().GetMute())


def _set_mute_state(flag: bool) -> None:
    _volume_interface().SetMute(1 if flag else 0, None)


def _get_brightness_pct() -> int:
    import screen_brightness_control as sbc  # type: ignore[import-untyped]

    values = sbc.get_brightness()
    if not values:
        raise RuntimeError("No controllable display found.")
    return int(values[0])


def _set_brightness_pct(pct: int) -> None:
    import screen_brightness_control as sbc

    sbc.set_brightness(pct)


def _lock_workstation() -> None:
    if ctypes.windll.user32.LockWorkStation() == 0:
        raise OSError(ctypes.get_last_error())


def _sleep_now() -> None:
    # SetSuspendState(Hibernate=False, ForceCritical=True, DisableWakeEvent=False)
    if ctypes.windll.powrprof.SetSuspendState(False, True, False) == 0:
        raise OSError(ctypes.get_last_error())


def _run_subprocess(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Thin wrapper so every shutdown/netsh/PnP call in this module goes
    through one mockable seam."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_S,
        check=False,
    )


def _list_interfaces() -> list[dict[str, str]]:
    """Parse `netsh interface show interface`'s fixed-width table into
    dicts. Format (columns are whitespace-separated, no reliable delimiter):

        Admin State    State          Type             Interface Name
        -------------------------------------------------------------------
        Enabled        Connected      Dedicated        Wi-Fi
    """
    result = _run_subprocess(["netsh", "interface", "show", "interface"])
    interfaces: list[dict[str, str]] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("-") or line.lower().startswith("admin"):
            continue
        parts = line.split(None, 3)
        if len(parts) == 4:
            admin_state, state, itype, name = parts
            interfaces.append(
                {"admin_state": admin_state, "state": state, "type": itype, "name": name}
            )
    return interfaces


def _find_wifi_interface() -> dict[str, str] | None:
    for iface in _list_interfaces():
        if "wireless" in iface["type"].lower() or "wi-fi" in iface["name"].lower():
            return iface
    return None


def _get_wifi_enabled() -> bool | None:
    iface = _find_wifi_interface()
    if iface is None:
        return None
    return iface["admin_state"].lower() == "enabled"


def _set_wifi_enabled(flag: bool) -> None:
    iface = _find_wifi_interface()
    name = iface["name"] if iface else "Wi-Fi"
    state = "enabled" if flag else "disabled"
    result = _run_subprocess(["netsh", "interface", "set", "interface", name, state])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "netsh failed")


# Bluetooth: Windows has no first-party CLI for radio on/off (unlike Wi-Fi's
# netsh). The WinRT `Windows.Devices.Radios` API is the "real" modern
# mechanism, but driving its IAsyncOperation from a synchronous tool call
# needs an asyncio bridge and WinRT apartment/threading setup that's fragile
# to run reliably from a worker thread on this hardware baseline, and it pulls
# in several extra `winrt-*` packages of unverified licence. Instead this
# drives the built-in `PnpDevice` PowerShell module (ships with Windows 10/11,
# no extra dependency) to enable/disable the Bluetooth radio device directly
# — the same effect, via a CLI mechanism consistent with how this module
# already shells out to netsh/shutdown. Requires an elevated shell to actually
# change state; read-only status queries do not.
def _bluetooth_radio_instance_id() -> str | None:
    script = (
        "Get-PnpDevice -Class Bluetooth -PresentOnly | "
        "Where-Object { $_.FriendlyName -match 'Radio|Adapter' } | "
        "Select-Object -First 1 -ExpandProperty InstanceId"
    )
    result = _run_subprocess(["powershell", "-NoProfile", "-Command", script])
    instance_id = result.stdout.strip()
    return instance_id or None


def _get_bluetooth_enabled() -> bool | None:
    instance_id = _bluetooth_radio_instance_id()
    if not instance_id:
        return None
    script = f"(Get-PnpDevice -InstanceId '{instance_id}').Status"
    result = _run_subprocess(["powershell", "-NoProfile", "-Command", script])
    status = result.stdout.strip()
    if not status:
        return None
    return status.upper() == "OK"


def _set_bluetooth_enabled(flag: bool) -> None:
    instance_id = _bluetooth_radio_instance_id()
    if not instance_id:
        raise RuntimeError("No Bluetooth radio found on this machine.")
    cmdlet = "Enable-PnpDevice" if flag else "Disable-PnpDevice"
    script = f"{cmdlet} -InstanceId '{instance_id}' -Confirm:$false"
    result = _run_subprocess(["powershell", "-NoProfile", "-Command", script])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"{cmdlet} failed (needs an admin shell).")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(tier="local", risk="safe", tags=["system", "audio"], undo="_undo_set_volume")
def set_volume(level: int | None = None, direction: str | None = None) -> str:
    """Set the system output volume to an absolute level or nudge it up/down.

    Args:
        level: Absolute volume level from 0 to 100.
        direction: "up" or "down" for a relative nudge instead of a level.
    """
    if level is None and direction is None:
        return "Specify either a volume level (0-100) or a direction ('up'/'down')."
    if level is not None and not 0 <= level <= 100:
        return "Volume level must be between 0 and 100."
    normalized_direction = direction.strip().lower() if direction is not None else None
    if normalized_direction is not None and normalized_direction not in ("up", "down"):
        return "Direction must be 'up' or 'down'."
    try:
        previous = _get_volume_pct()
        if level is not None:
            target = level
        else:
            step = _VOLUME_STEP_PCT if normalized_direction == "up" else -_VOLUME_STEP_PCT
            target = max(0, min(100, previous + step))
        UNDO_STACK.push(
            "set_volume", f"Restore volume to {previous}%", lambda: _undo_set_volume(previous)
        )
        _set_volume_pct(target)
        return f"Volume set to {target}%."
    except Exception as exc:
        return f"Could not change volume: {exc}"


def _undo_set_volume(previous: int) -> str:
    try:
        _set_volume_pct(previous)
        return f"Volume restored to {previous}%."
    except Exception as exc:
        return f"Could not undo volume change: {exc}"


@tool(tier="local", risk="safe", tags=["system", "audio"], undo="_undo_mute")
def mute(state: str | None = None) -> str:
    """Mute or unmute system audio, or toggle it if no state is given.

    Args:
        state: "on" to mute, "off" to unmute, omit to toggle the current state.
    """
    normalized = state.strip().lower() if state is not None else None
    if normalized is not None and normalized not in ("on", "off"):
        return "Mute state must be 'on', 'off', or omitted to toggle."
    try:
        previous = _get_mute_state()
        target = (not previous) if normalized is None else normalized == "on"
        UNDO_STACK.push(
            "mute",
            f"Set mute back to {'on' if previous else 'off'}",
            lambda: _undo_mute(previous),
        )
        _set_mute_state(target)
        return f"Audio {'muted' if target else 'unmuted'}."
    except Exception as exc:
        return f"Could not change mute state: {exc}"


def _undo_mute(previous: bool) -> str:
    try:
        _set_mute_state(previous)
        return f"Mute restored to {'on' if previous else 'off'}."
    except Exception as exc:
        return f"Could not undo mute change: {exc}"


@tool(tier="local", risk="safe", tags=["system", "audio"])
def get_volume() -> str:
    """Report the current system output volume and mute state."""
    try:
        pct = _get_volume_pct()
        muted = _get_mute_state()
        return f"Volume is {pct}%{' (muted)' if muted else ''}."
    except Exception as exc:
        return f"Could not read volume: {exc}"


@tool(tier="local", risk="safe", tags=["system", "display"], undo="_undo_set_brightness")
def set_brightness(level: int | None = None, direction: str | None = None) -> str:
    """Set screen brightness to an absolute level or nudge it up/down.

    Args:
        level: Absolute brightness level from 0 to 100.
        direction: "up" or "down" for a relative nudge instead of a level.
    """
    if level is None and direction is None:
        return "Specify either a brightness level (0-100) or a direction ('up'/'down')."
    if level is not None and not 0 <= level <= 100:
        return "Brightness level must be between 0 and 100."
    normalized_direction = direction.strip().lower() if direction is not None else None
    if normalized_direction is not None and normalized_direction not in ("up", "down"):
        return "Direction must be 'up' or 'down'."
    try:
        previous = _get_brightness_pct()
        if level is not None:
            target = level
        else:
            step = _BRIGHTNESS_STEP_PCT if normalized_direction == "up" else -_BRIGHTNESS_STEP_PCT
            target = max(0, min(100, previous + step))
        UNDO_STACK.push(
            "set_brightness",
            f"Restore brightness to {previous}%",
            lambda: _undo_set_brightness(previous),
        )
        _set_brightness_pct(target)
        return f"Brightness set to {target}%."
    except Exception as exc:
        return f"Could not change brightness: {exc}"


def _undo_set_brightness(previous: int) -> str:
    try:
        _set_brightness_pct(previous)
        return f"Brightness restored to {previous}%."
    except Exception as exc:
        return f"Could not undo brightness change: {exc}"


@tool(tier="local", risk="safe", tags=["system", "display"])
def get_brightness() -> str:
    """Report the current screen brightness level."""
    try:
        pct = _get_brightness_pct()
        return f"Brightness is {pct}%."
    except Exception as exc:
        return f"Could not read brightness: {exc}"


@tool(tier="local", risk="safe", tags=["system", "power"])
def lock_screen() -> str:
    """Lock the Windows session immediately."""
    try:
        _lock_workstation()
        return "Screen locked."
    except Exception as exc:
        return f"Could not lock the screen: {exc}"


@tool(tier="local", risk="safe", tags=["system", "power"])
def sleep() -> str:
    """Put the computer to sleep immediately."""
    try:
        _sleep_now()
        return "Going to sleep."
    except Exception as exc:
        return f"Could not put the computer to sleep: {exc}"


@tool(tier="local", risk="confirm", tags=["system", "power"], undo="_abort_shutdown")
def shutdown(delay_s: int = 30) -> str:
    """Schedule a shutdown after a delay, so there's a window to cancel it.

    Args:
        delay_s: Seconds to wait before shutting down; also the undo window.
    """
    if delay_s < 0:
        return "delay_s must be zero or positive."
    try:
        UNDO_STACK.push(
            "shutdown", f"Abort the scheduled shutdown ({delay_s}s window)", _abort_shutdown
        )
        result = _run_subprocess(["shutdown", "/s", "/t", str(delay_s)])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "shutdown command failed")
        return f"Shutting down in {delay_s} seconds. Say 'undo' to cancel."
    except Exception as exc:
        return f"Could not schedule shutdown: {exc}"


@tool(tier="local", risk="confirm", tags=["system", "power"], undo="_abort_shutdown")
def restart(delay_s: int = 30) -> str:
    """Schedule a restart after a delay, so there's a window to cancel it.

    Args:
        delay_s: Seconds to wait before restarting; also the undo window.
    """
    if delay_s < 0:
        return "delay_s must be zero or positive."
    try:
        UNDO_STACK.push(
            "restart", f"Abort the scheduled restart ({delay_s}s window)", _abort_shutdown
        )
        result = _run_subprocess(["shutdown", "/r", "/t", str(delay_s)])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "shutdown command failed")
        return f"Restarting in {delay_s} seconds. Say 'undo' to cancel."
    except Exception as exc:
        return f"Could not schedule restart: {exc}"


def _abort_shutdown() -> str:
    """Shared inverse for shutdown() and restart(): `shutdown /a` genuinely
    reverses either, as long as it runs before the delay elapses."""
    try:
        result = _run_subprocess(["shutdown", "/a"])
        if result.returncode != 0:
            return f"Could not abort shutdown/restart: {result.stderr.strip()}"
        return "Scheduled shutdown/restart cancelled."
    except Exception as exc:
        return f"Could not abort shutdown/restart: {exc}"


@tool(tier="local", risk="safe", tags=["system", "network"], undo="_undo_wifi_toggle")
def wifi_toggle(state: str) -> str:
    """Turn the Wi-Fi radio on or off.

    Args:
        state: "on" to enable Wi-Fi, "off" to disable it.
    """
    normalized = (state or "").strip().lower()
    if normalized not in ("on", "off"):
        return "Wi-Fi state must be 'on' or 'off'."
    try:
        previous = _get_wifi_enabled()
        UNDO_STACK.push(
            "wifi_toggle", "Restore previous Wi-Fi state", lambda: _undo_wifi_toggle(previous)
        )
        _set_wifi_enabled(normalized == "on")
        return f"Wi-Fi turned {normalized}."
    except Exception as exc:
        return f"Could not toggle Wi-Fi: {exc}"


def _undo_wifi_toggle(previous: bool | None) -> str:
    if previous is None:
        return "Could not undo Wi-Fi toggle: previous state was unknown."
    try:
        _set_wifi_enabled(previous)
        return f"Wi-Fi turned back {'on' if previous else 'off'}."
    except Exception as exc:
        return f"Could not undo Wi-Fi toggle: {exc}"


@tool(tier="local", risk="safe", tags=["system", "network"])
def wifi_status() -> str:
    """Report whether the Wi-Fi radio is currently on or off."""
    try:
        enabled = _get_wifi_enabled()
        if enabled is None:
            return "No Wi-Fi adapter found."
        return f"Wi-Fi is {'on' if enabled else 'off'}."
    except Exception as exc:
        return f"Could not read Wi-Fi status: {exc}"


@tool(tier="local", risk="safe", tags=["system", "bluetooth"], undo="_undo_bluetooth_toggle")
def bluetooth_toggle(state: str) -> str:
    """Turn the Bluetooth radio on or off.

    Args:
        state: "on" to enable Bluetooth, "off" to disable it.
    """
    normalized = (state or "").strip().lower()
    if normalized not in ("on", "off"):
        return "Bluetooth state must be 'on' or 'off'."
    try:
        previous = _get_bluetooth_enabled()
        UNDO_STACK.push(
            "bluetooth_toggle",
            "Restore previous Bluetooth state",
            lambda: _undo_bluetooth_toggle(previous),
        )
        _set_bluetooth_enabled(normalized == "on")
        return f"Bluetooth turned {normalized}."
    except Exception as exc:
        return f"Could not toggle Bluetooth: {exc}"


def _undo_bluetooth_toggle(previous: bool | None) -> str:
    if previous is None:
        return "Could not undo Bluetooth toggle: previous state was unknown."
    try:
        _set_bluetooth_enabled(previous)
        return f"Bluetooth turned back {'on' if previous else 'off'}."
    except Exception as exc:
        return f"Could not undo Bluetooth toggle: {exc}"


@tool(tier="local", risk="safe", tags=["system", "bluetooth"])
def bluetooth_status() -> str:
    """Report whether the Bluetooth radio is currently on or off."""
    try:
        enabled = _get_bluetooth_enabled()
        if enabled is None:
            return "No Bluetooth radio found."
        return f"Bluetooth is {'on' if enabled else 'off'}."
    except Exception as exc:
        return f"Could not read Bluetooth status: {exc}"


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------
#
# Added in Phase 3, but it belongs to the Phase 2 intent set: battery_status
# had a grammar template, examples in all three languages and golden cases
# from the start, and no tool behind any of them. Nothing caught it because
# the golden runner graded against a fake registry built *from the golden set
# itself* — so the tool existed by construction, and routing "how much battery
# do I have" returned a match that could never execute. The runner now uses
# the real registry (tests/test_router.py::test_every_golden_tool_is_registered).


def _battery_state() -> tuple[int, bool, int | None] | None:
    """(percent, plugged_in, seconds_left) or None on a desktop with no
    battery. Isolated like the other OS boundaries so tests can fake it."""
    import psutil

    battery = psutil.sensors_battery()
    if battery is None:
        return None
    raw = battery.secsleft
    # psutil reports POWER_TIME_UNLIMITED/UNKNOWN as negative sentinels rather
    # than None, and Windows returns UNKNOWN while a charge estimate settles.
    unknown = (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN)
    seconds: int | None = None if (raw in unknown or raw < 0) else int(raw)
    return int(round(battery.percent)), bool(battery.power_plugged), seconds


@tool(tier="local", risk="safe", tags=["system", "power"])
def battery_status() -> str:
    """Report the current battery level and whether it is charging."""
    try:
        state = _battery_state()
    except Exception as exc:
        return f"Could not read the battery: {exc}"
    if state is None:
        return "This machine doesn't have a battery."

    percent, plugged, seconds = state
    if plugged:
        charged = " and fully charged" if percent >= 99 else " and charging"
        return f"Battery is at {percent}%{charged}."
    if seconds is not None:
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        if hours:
            left = f"about {hours} hour{'s' if hours != 1 else ''} {minutes} minutes"
        else:
            left = f"about {minutes} minutes"
        return f"Battery is at {percent}%, {left} left."
    return f"Battery is at {percent}%, on battery power."


# ---------------------------------------------------------------------------
# Undo (Phase 3)
# ---------------------------------------------------------------------------
#
# Lives here rather than in a new module: it is a command about the machine's
# state, like lock/sleep, and repo-structure discipline
# (engineering-standards.md) says a new capability belongs in an existing
# module unless it genuinely needs its own.


@tool(tier="local", risk="safe", tags=["system", "undo"])
def undo_last() -> str:
    """Reverse the last action that changed something."""
    try:
        if not UNDO_STACK.can_undo():
            return "There's nothing to undo."
        return UNDO_STACK.undo_last()
    except Exception as exc:
        return f"Could not undo the last action: {exc}"


@tool(tier="local", risk="safe", tags=["system", "undo"])
def what_can_i_undo() -> str:
    """Say what the next undo would reverse, without reversing it."""
    try:
        description = UNDO_STACK.peek_description()
        if description is None:
            return "There's nothing to undo."
        return f"The next undo would: {description.lower()}."
    except Exception as exc:
        return f"Could not check the undo history: {exc}"
