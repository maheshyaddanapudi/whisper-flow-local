"""Command-line entry point (``whisper-flow``).

Thin wrapper: parses args, loads config, and dispatches. Phase 0 ships the
non-daemon commands (doctor, config, gen-docs). Phase 1 adds the daemon control
verbs (start, toggle, cancel, status, paste-last) which forward to the running
daemon over the IPC socket.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import __version__
from .config import Config, ConfigError, default_config_path, dumps, generate_docs, load

# Daemon control verbs forwarded over IPC.
_CONTROL_VERBS = (
    "toggle",
    "ptt-down",
    "ptt-up",
    "cancel",
    "status",
    "paste-last",
    "paste-last-raw",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="whisper-flow",
        description="Fully local dictation: hotkey -> Whisper -> Ollama cleanup -> any app.",
    )
    parser.add_argument("--version", action="version", version=f"whisper-flow-local {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.toml (default: ~/.config/whisper-flow/config.toml).",
    )
    parser.add_argument(
        "--socket",
        type=Path,
        default=None,
        help="Path to the daemon IPC socket (default: runtime dir).",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="For toggle/ptt-up: inject the raw transcript, skipping LLM cleanup.",
    )
    parser.add_argument(
        "--command",
        dest="command_mode",
        action="store_true",
        help="For toggle/ptt-up: command mode — transform the selected text per what you say.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Report available STT/Ollama/injection/hotkey capabilities.")

    cfg = sub.add_parser("config", help="Manage configuration.")
    cfg_sub = cfg.add_subparsers(dest="config_command", required=True)
    cfg_sub.add_parser("path", help="Print the config file path.")
    cfg_sub.add_parser("show", help="Print the effective config as TOML.")
    init = cfg_sub.add_parser("init", help="Write a default config file.")
    init.add_argument("--force", action="store_true", help="Overwrite an existing file.")

    sub.add_parser("gen-docs", help="Print the config reference (Markdown) to stdout.")

    dct = sub.add_parser("dict", help="Manage the personal dictionary.")
    dct_sub = dct.add_subparsers(dest="dict_command", required=True)
    dct_sub.add_parser("show", help="Print the dictionary path and vocabulary.")
    add = dct_sub.add_parser("add", help="Add a vocabulary word.")
    add.add_argument("word", help="The word or phrase to add.")

    bench = sub.add_parser("bench", help="Benchmark STT models on this hardware.")
    bench.add_argument("--audio", required=True, type=Path, help="Sample WAV file to transcribe.")
    bench.add_argument("--models", nargs="+", help="Model names to test (default: configured).")

    sub.add_parser("start", help="Run the dictation daemon (foreground).")
    for verb in _CONTROL_VERBS:
        sub.add_parser(verb, help=f"Send '{verb}' to the running daemon.")

    log = sub.add_parser("log", help="Show what was recently sent to the local LLM.")
    log.add_argument("-n", type=int, default=10, help="How many recent calls to show.")

    correct = sub.add_parser(
        "correct", help="Teach a correction (misheard -> right); applied automatically after."
    )
    correct.add_argument("source", nargs="?", help="What it keeps getting wrong (word/phrase).")
    correct.add_argument("target", nargs="?", help="What it should be instead.")
    correct.add_argument(
        "--last",
        metavar="FIXED",
        help="Correct the last dictation to FIXED; the differences are learned automatically.",
    )

    return parser


def _resolve_config_path(args: argparse.Namespace) -> Path:
    return args.config if args.config is not None else default_config_path()


def _cmd_doctor(config: Config) -> int:
    # Imported lazily so `doctor` is the only path that probes Ollama.
    from .deps import render_report
    from .permissions import render as render_permissions

    print(render_report(config))
    perm = render_permissions(platform.system())
    if perm:
        print()
        print(perm)
    return 0


def _cmd_config(args: argparse.Namespace, config: Config, path: Path) -> int:
    if args.config_command == "path":
        print(path)
        return 0
    if args.config_command == "show":
        print(dumps(config), end="")
        return 0
    if args.config_command == "init":
        if path.exists() and not args.force:
            print(f"refusing to overwrite {path} (use --force)", file=sys.stderr)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dumps(config), encoding="utf-8")
        print(f"wrote {path}")
        return 0
    return 1  # pragma: no cover - argparse enforces a valid subcommand


def _cmd_gen_docs() -> int:
    print(generate_docs(), end="")
    return 0


def _cmd_dict(args: argparse.Namespace, config: Config) -> int:
    from .builder import dictionary_path
    from .dictionary.replacements import DictionaryError, load, quick_add

    path = dictionary_path(config)
    if args.dict_command == "show":
        dictionary = load(path)
        print(f"dictionary: {path}")
        print("vocab: " + (", ".join(dictionary.vocab) if dictionary.vocab else "(empty)"))
        return 0
    # add
    try:
        updated = quick_add(path, args.word)
    except DictionaryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"added '{args.word}' ({len(updated.vocab)} vocab entries)")
    return 0


def _cmd_correct(args: argparse.Namespace, config: Config) -> int:
    from .builder import dictionary_path
    from .dictionary.replacements import DictionaryError, add_replacement

    path = dictionary_path(config)
    if args.last is not None:
        return _correct_from_last(args, path)
    if not (args.source and args.target):
        print("error: give SOURCE and TARGET, or use --last", file=sys.stderr)
        return 1
    try:
        add_replacement(path, args.source, args.target)
    except DictionaryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"learned: '{args.source}' -> '{args.target}' (applied automatically from now on)")
    return 0


def _correct_from_last(args: argparse.Namespace, path: Path) -> int:
    from .dictionary.replacements import learn_corrections
    from .ipc import IPCError, send

    try:
        resp = send(_resolve_socket_path(args), "status")
    except IPCError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    before = resp.get("data", {}).get("last_text", "") if resp.get("ok") else ""
    if not before:
        print("error: no last dictation to correct", file=sys.stderr)
        return 1
    pairs = learn_corrections(path, before, args.last)
    if not pairs:
        print("no changes to learn (texts already match)")
        return 0
    for source, target in pairs:
        print(f"learned: '{source}' -> '{target}'")
    return 0


def _resolve_socket_path(args: argparse.Namespace) -> Path:
    from .ipc import default_socket_path

    result: Path = args.socket if args.socket is not None else default_socket_path()
    return result


def _cmd_send(args: argparse.Namespace) -> int:
    from .ipc import IPCError, send

    verb_args: dict[str, object] = {}
    if args.raw:
        verb_args["clean"] = False
    if args.command_mode:
        verb_args["command"] = True
    try:
        resp = send(_resolve_socket_path(args), args.command, verb_args)
    except IPCError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if resp.get("ok"):
        print(json.dumps(resp.get("data", {})))
        return 0
    print(f"error: {resp.get('error', 'unknown')}", file=sys.stderr)
    return 1


def _cmd_bench(config: Config, args: argparse.Namespace) -> int:
    import wave

    from .stt.bench import format_table, run_bench

    if not args.audio.exists():
        print(f"error: audio file not found: {args.audio}", file=sys.stderr)
        return 1
    models = args.models or [str(config.get("stt.model"))]
    with wave.open(str(args.audio), "rb") as wav:
        audio_seconds = wav.getnframes() / float(wav.getframerate())
    timer = _make_bench_timer(config, args.audio)
    results = run_bench(models, timer)
    print(format_table(results, audio_seconds))
    return 0


def _make_bench_timer(  # pragma: no cover - hardware seam
    config: Config, audio: Path
) -> Callable[[str], float]:
    import time

    from .audio import AudioBuffer
    from .build import _build_stt

    def timer(model: str) -> float:
        cfg = Config(dict(config.data))
        cfg.data.setdefault("stt", {})["model"] = model
        backend = _build_stt(cfg)
        import wave

        import numpy as np

        with wave.open(str(audio), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            buf = AudioBuffer(data=data, sample_rate=wav.getframerate())
        start = time.monotonic()
        backend.transcribe(buf)
        return time.monotonic() - start

    return timer


def _cmd_log(args: argparse.Namespace) -> int:
    from .ipc import IPCError, send

    try:
        resp = send(_resolve_socket_path(args), "log", {"n": args.n})
    except IPCError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not resp.get("ok"):
        print(f"error: {resp.get('error', 'unknown')}", file=sys.stderr)
        return 1
    calls = resp.get("data", {}).get("calls", [])
    if not calls:
        print("no LLM calls recorded yet")
        return 0
    for i, call in enumerate(calls):
        print(f"--- call {i + 1} ({call['kind']}) ---")
        print(f"  system: {call['system']}")
        print(f"  sent:   {call['user']}")
        print(f"  got:    {call['output']}")
    return 0


def _cmd_start(config: Config, args: argparse.Namespace) -> int:
    from .build import build_daemon

    daemon = build_daemon(config)
    print(f"whisper-flow daemon listening on {daemon._server.path}")
    daemon.run()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    path = _resolve_config_path(args)

    try:
        config = load(path)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if args.command == "doctor":
        return _cmd_doctor(config)
    if args.command == "config":
        return _cmd_config(args, config, path)
    if args.command == "gen-docs":
        return _cmd_gen_docs()
    if args.command == "dict":
        return _cmd_dict(args, config)
    if args.command == "correct":
        return _cmd_correct(args, config)
    if args.command == "bench":
        return _cmd_bench(config, args)
    if args.command == "start":
        return _cmd_start(config, args)
    if args.command == "log":
        return _cmd_log(args)
    if args.command in _CONTROL_VERBS:
        return _cmd_send(args)
    return 1  # pragma: no cover - argparse enforces a valid command


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
