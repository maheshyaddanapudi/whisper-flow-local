"""Personal dictionary: STT vocabulary hints + deterministic replacements.

Two tiers (Superwhisper + nerd-dictation traits):

1. **Vocabulary hints** — a small list (capped, since overloading degrades STT)
   seeded into Whisper's ``initial_prompt`` so proper nouns/jargon transcribe
   correctly in the first place.
2. **Deterministic replacements** — applied AFTER transcription and BEFORE the
   LLM, in a fixed layered order so results are reliable regardless of cleanup:
     a. multi-word phrase fixes (longest first),
     b. spoken-punctuation map (with leading-space cleanup),
     c. single-word map, where an empty replacement deletes the word.

Stored as one TOML file (diffable/syncable). All pure logic, fully tested.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

VOCAB_HINT_CAP = 20
"""Max vocabulary entries fed to initial_prompt; more degrades recognition."""


class DictionaryError(ValueError):
    """Raised when a dictionary file is malformed."""


@dataclass(frozen=True)
class Dictionary:
    vocab: tuple[str, ...] = ()
    phrases: tuple[tuple[str, str], ...] = ()  # (spoken, written), applied longest-first
    punctuation: tuple[tuple[str, str], ...] = ()  # (spoken, symbol)
    words: tuple[tuple[str, str], ...] = ()  # (spoken, written); "" deletes


@dataclass
class _MutableDict:
    vocab: list[str] = field(default_factory=list)
    phrases: dict[str, str] = field(default_factory=dict)
    punctuation: dict[str, str] = field(default_factory=dict)
    words: dict[str, str] = field(default_factory=dict)


def _as_str_map(section: object, name: str) -> dict[str, str]:
    if not isinstance(section, dict):
        raise DictionaryError(f"[{name}] must be a table")
    out: dict[str, str] = {}
    for key, value in section.items():
        if not isinstance(value, str):
            raise DictionaryError(f"{name}.{key} must map to a string")
        out[str(key)] = value
    return out


def load(path: Path | None) -> Dictionary:
    """Load a dictionary TOML, or return an empty dictionary if absent."""
    if path is None or not path.exists():
        return Dictionary()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise DictionaryError(f"{path}: invalid TOML: {exc}") from exc
    vocab_raw = raw.get("vocab", [])
    if not isinstance(vocab_raw, list) or not all(isinstance(v, str) for v in vocab_raw):
        raise DictionaryError("vocab must be a list of strings")
    phrases = _as_str_map(raw.get("phrases", {}), "phrases")
    punctuation = _as_str_map(raw.get("punctuation", {}), "punctuation")
    words = _as_str_map(raw.get("words", {}), "words")
    return Dictionary(
        vocab=tuple(vocab_raw),
        phrases=tuple(phrases.items()),
        punctuation=tuple(punctuation.items()),
        words=tuple(words.items()),
    )


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def dumps(dictionary: Dictionary) -> str:
    """Serialize a dictionary back to TOML (used by quick-add)."""
    lines = ["# whisper-flow-local personal dictionary", ""]
    vocab = ", ".join(f'"{_toml_escape(v)}"' for v in dictionary.vocab)
    lines.append(f"vocab = [{vocab}]")
    for section, pairs in (
        ("phrases", dictionary.phrases),
        ("punctuation", dictionary.punctuation),
        ("words", dictionary.words),
    ):
        if pairs:
            lines.append("")
            lines.append(f"[{section}]")
            lines.extend(f'"{_toml_escape(k)}" = "{_toml_escape(v)}"' for k, v in pairs)
    return "\n".join(lines) + "\n"


def initial_prompt(dictionary: Dictionary, cap: int = VOCAB_HINT_CAP) -> str | None:
    """Build a Whisper ``initial_prompt`` from capped vocabulary hints."""
    vocab = list(dictionary.vocab)[:cap]
    if not vocab:
        return None
    return "Vocabulary: " + ", ".join(vocab) + "."


def quick_add(path: Path, word: str) -> Dictionary:
    """Add a vocabulary word to the dictionary file (dedup), returning the new one."""
    word = word.strip()
    if not word:
        raise DictionaryError("cannot add an empty word")
    current = load(path)
    if word in current.vocab:
        return current
    updated = Dictionary(
        vocab=(*current.vocab, word),
        phrases=current.phrases,
        punctuation=current.punctuation,
        words=current.words,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(updated), encoding="utf-8")
    return updated


def add_replacement(path: Path, source: str, target: str) -> Dictionary:
    """Teach a correction: ``source`` -> ``target``, persisted to the dictionary.

    A multi-word source becomes a phrase rule (applied first, longest-first); a
    single word becomes a word rule. Re-adding the same source updates its
    target. This is the lightweight "never the same mistake twice" loop: correct
    it once and the fix applies deterministically from then on.
    """
    source = source.strip()
    if not source:
        raise DictionaryError("correction source cannot be empty")
    current = load(path)
    is_phrase = " " in source
    pairs = dict(current.phrases if is_phrase else current.words)
    pairs[source] = target
    updated = Dictionary(
        vocab=current.vocab,
        phrases=tuple(pairs.items()) if is_phrase else current.phrases,
        punctuation=current.punctuation,
        words=current.words if is_phrase else tuple(pairs.items()),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(updated), encoding="utf-8")
    return updated


class ReplacementEngine:
    """Applies the layered deterministic replacements to a transcript."""

    def __init__(self, dictionary: Dictionary) -> None:
        # Phrases longest-first so "cube it all" wins over "cube".
        self._phrases = sorted(dictionary.phrases, key=lambda kv: len(kv[0]), reverse=True)
        self._punctuation = list(dictionary.punctuation)
        self._words = list(dictionary.words)

    def apply(self, text: str) -> str:
        text = self._apply_phrases(text)
        text = self._apply_punctuation(text)
        text = self._apply_words(text)
        return self._tidy_spaces(text)

    def _apply_phrases(self, text: str) -> str:
        for spoken, written in self._phrases:
            text = re.sub(re.escape(spoken), written, text, flags=re.IGNORECASE)
        return text

    def _apply_punctuation(self, text: str) -> str:
        # Consume any leading whitespace so "hello comma" -> "hello,".
        for spoken, symbol in self._punctuation:
            pattern = r"\s*\b" + re.escape(spoken) + r"\b"
            text = re.sub(pattern, symbol, text, flags=re.IGNORECASE)
        return text

    def _apply_words(self, text: str) -> str:
        for spoken, written in self._words:
            pattern = r"\b" + re.escape(spoken) + r"\b"
            text = re.sub(pattern, written, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _tidy_spaces(text: str) -> str:
        # Collapse doubled spaces left by word deletions; drop space before ,.?!;:
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\s+([,.?!;:])", r"\1", text)
        return text.strip()
