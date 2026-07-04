"""Command-line entry point (``whisper-flow``).

Thin wrapper: parses args, loads config, and dispatches. Phase 0 ships the
non-daemon commands (doctor, config, gen-docs). Phase 1 adds the daemon control
verbs (start, toggle, cancel, status, paste-last) which forward to the running
daemon over the IPC socket.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
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

    sub.add_parser("start", help="Run the dictation daemon (foreground).")
    for verb in _CONTROL_VERBS:
        sub.add_parser(verb, help=f"Send '{verb}' to the running daemon.")

    return parser


def _resolve_config_path(args: argparse.Namespace) -> Path:
    return args.config if args.config is not None else default_config_path()


def _cmd_doctor(config: Config) -> int:
    # Imported lazily so `doctor` is the only path that probes Ollama.
    from .deps import render_report

    print(render_report(config))
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


def _resolve_socket_path(args: argparse.Namespace) -> Path:
    from .ipc import default_socket_path

    result: Path = args.socket if args.socket is not None else default_socket_path()
    return result


def _cmd_send(args: argparse.Namespace) -> int:
    from .ipc import IPCError, send

    verb_args = {"clean": False} if args.raw else {}
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
    if args.command == "start":
        return _cmd_start(config, args)
    if args.command in _CONTROL_VERBS:
        return _cmd_send(args)
    return 1  # pragma: no cover - argparse enforces a valid command


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
