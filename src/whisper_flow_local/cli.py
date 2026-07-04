"""Command-line entry point (``whisper-flow``).

Thin wrapper: parses args, loads config, and dispatches. Phase 0 ships the
non-daemon commands (doctor, config, gen-docs). Phase 1 adds the daemon control
verbs (start, toggle, cancel, status, paste-last) which forward to the running
daemon over the IPC socket.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import Config, ConfigError, default_config_path, dumps, generate_docs, load


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
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Report available STT/Ollama/injection/hotkey capabilities.")

    cfg = sub.add_parser("config", help="Manage configuration.")
    cfg_sub = cfg.add_subparsers(dest="config_command", required=True)
    cfg_sub.add_parser("path", help="Print the config file path.")
    cfg_sub.add_parser("show", help="Print the effective config as TOML.")
    init = cfg_sub.add_parser("init", help="Write a default config file.")
    init.add_argument("--force", action="store_true", help="Overwrite an existing file.")

    sub.add_parser("gen-docs", help="Print the config reference (Markdown) to stdout.")

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
    return 1  # pragma: no cover - argparse enforces a valid command


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
