"""Assemble a live daemon from config with real hardware adapters (thin seam).

This is the only place the optional hardware libraries are constructed. It is
excluded from coverage because it imports device libraries absent in CI; the
*decisions* it relies on (chain ordering, config mapping, STT selection) are
tested via :mod:`whisper_flow_local.builder` with fakes.
"""

from __future__ import annotations

import os
import platform

from .audio_capture import SoundDeviceSource
from .builder import (
    build_cleanup_engine,
    build_controller_config,
    build_dictionary,
    build_injection_chain,
    build_profile_resolver,
    build_profiles,
    build_replacement,
    resolve_stt_backend_name,
)
from .config import Config
from .controller import Controller, _Deps
from .daemon import Daemon
from .history import History
from .hotkeys.base import HotkeyListener
from .inject.base import Injector
from .inject.clipboard import ClipboardInjector
from .inject.copyonly import CopyOnlyInjector
from .inject.system import (
    KeystrokeInjector,
    SystemClipboard,
    make_paster,
    make_selection_reader,
)
from .ipc import default_socket_path
from .stt.base import STTBackend


def _build_stt(config: Config) -> STTBackend:
    name = resolve_stt_backend_name(config, platform.system())
    if name == "whispercpp":
        from .stt.whispercpp import WhisperCppBackend

        return WhisperCppBackend(str(config.get("stt.model")))
    from .stt.fasterwhisper import FasterWhisperBackend

    return FasterWhisperBackend(
        str(config.get("stt.model")),
        device=str(config.get("stt.device")),
        compute_type=str(config.get("stt.compute_type")),
    )


def _build_injectors(clipboard: SystemClipboard) -> dict[str, Injector]:
    injectors: dict[str, Injector] = {
        "clipboard": ClipboardInjector(clipboard, make_paster()),
        "keystrokes": KeystrokeInjector(),
        "copy_only": CopyOnlyInjector(clipboard),
    }
    # On Linux, add a detected CLI injector (xdotool/wtype/ydotool) under the
    # name "keystrokes" so it takes precedence over pynput where available.
    if platform.system() == "Linux":
        import shutil

        from .inject.linux import CommandInjector, detect_session_type, select_tool

        tool = select_tool(detect_session_type(os.environ), shutil.which)
        if tool is not None:
            injectors["keystrokes"] = CommandInjector(tool)
    return injectors


def _build_hotkey_listener(config: Config, controller: Controller) -> HotkeyListener:
    from .hotkeys.base import parse_hotkey
    from .hotkeys.pynput_listener import PynputHotkeyListener

    hotkey = parse_hotkey(str(config.get("hotkey.primary")))
    return PynputHotkeyListener(hotkey, controller.on_hotkey_press, controller.on_hotkey_release)


def build_daemon(config: Config) -> Daemon:
    clipboard = SystemClipboard()
    chain = build_injection_chain(list(config.get("inject.chain")), _build_injectors(clipboard))
    audio = SoundDeviceSource(int(config.get("audio.sample_rate")), str(config.get("audio.device")))
    from .frontmost import detect as detect_frontmost
    from .notifier import StateNotifier
    from .transparency import TransparencyLog
    from .ui.cues import make_cue_hooks, system_player

    log = TransparencyLog(int(config.get("transparency.size")))
    record = log.record if bool(config.get("transparency.enabled")) else None
    engine = build_cleanup_engine(config, record=record)
    dictionary = build_dictionary(config)
    profiles = build_profiles(config)
    notifier = StateNotifier()
    notify = make_cue_hooks(system_player()) if bool(config.get("audio.cues")) else {}
    deps = _Deps(
        audio=audio,
        stt=_build_stt(config),
        injection=chain,
        history=History(int(config.get("history.size"))),
        cleanup=engine.clean if engine is not None else None,
        replace=build_replacement(dictionary),
        instruct=engine.instruct if engine is not None else None,
        get_selection=make_selection_reader(clipboard),
        resolve_profile=build_profile_resolver(profiles, detect_frontmost),
        transparency=log if bool(config.get("transparency.enabled")) else None,
        on_state_change=notifier,
        notify=notify,
    )
    controller = Controller(build_controller_config(config, dictionary), deps)
    listener = None
    if str(config.get("hotkey.backend")) != "none":
        listener = _build_hotkey_listener(config, controller)
    daemon = Daemon(controller, default_socket_path(), hotkey_listener=listener)
    if bool(config.get("ui.enabled")):
        from .ui.tray import TrayApp

        tray = TrayApp(controller, on_quit=daemon.stop)
        notifier.register(tray.on_state_change)
        daemon.attach_tray(tray)
    return daemon
