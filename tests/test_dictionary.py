"""Tests for the personal dictionary: load/dump, vocab hints, replacements."""

from __future__ import annotations

import pytest

from whisper_flow_local.dictionary.replacements import (
    Dictionary,
    DictionaryError,
    ReplacementEngine,
    add_replacement,
    dumps,
    initial_prompt,
    load,
    quick_add,
)


def _write(tmp_path, text: str):
    p = tmp_path / "dictionary.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_absent_returns_empty() -> None:
    assert load(None) == Dictionary()


def test_load_missing_file_returns_empty(tmp_path) -> None:
    assert load(tmp_path / "nope.toml") == Dictionary()


def test_load_full_dictionary(tmp_path) -> None:
    p = _write(
        tmp_path,
        """
        vocab = ["MySQL", "Kubernetes"]
        [phrases]
        "my sequel" = "MySQL"
        [punctuation]
        "comma" = ","
        [words]
        "gonna" = "going to"
        "basically" = ""
        """,
    )
    d = load(p)
    assert d.vocab == ("MySQL", "Kubernetes")
    assert ("my sequel", "MySQL") in d.phrases
    assert ("comma", ",") in d.punctuation
    assert ("basically", "") in d.words


def test_load_rejects_bad_vocab(tmp_path) -> None:
    with pytest.raises(DictionaryError, match="vocab"):
        load(_write(tmp_path, "vocab = [1, 2]"))


def test_load_rejects_non_table_section(tmp_path) -> None:
    with pytest.raises(DictionaryError, match="phrases"):
        load(_write(tmp_path, "phrases = 5"))


def test_load_rejects_non_string_value(tmp_path) -> None:
    with pytest.raises(DictionaryError, match=r"words\.gonna"):
        load(_write(tmp_path, "[words]\ngonna = 5"))


def test_load_rejects_invalid_toml(tmp_path) -> None:
    with pytest.raises(DictionaryError, match="invalid TOML"):
        load(_write(tmp_path, "= = ="))


def test_dumps_roundtrip(tmp_path) -> None:
    d = Dictionary(
        vocab=("MySQL",),
        phrases=(("my sequel", "MySQL"),),
        punctuation=(("comma", ","),),
        words=(("basically", ""),),
    )
    p = tmp_path / "d.toml"
    p.write_text(dumps(d), encoding="utf-8")
    assert load(p) == d


def test_dumps_escapes_special_chars() -> None:
    d = Dictionary(words=(("newline", "a\nb"),))
    assert "\\n" in dumps(d)


def test_initial_prompt_caps_vocab() -> None:
    d = Dictionary(vocab=tuple(f"w{i}" for i in range(30)))
    prompt = initial_prompt(d, cap=5)
    assert prompt is not None
    assert prompt.count(",") == 4  # 5 items -> 4 separators
    assert prompt.startswith("Vocabulary: ")


def test_initial_prompt_empty_is_none() -> None:
    assert initial_prompt(Dictionary()) is None


def test_quick_add_creates_and_dedups(tmp_path) -> None:
    p = tmp_path / "sub" / "dictionary.toml"
    d = quick_add(p, "Anthropic")
    assert d.vocab == ("Anthropic",)
    assert p.exists()
    # adding again is a no-op
    d2 = quick_add(p, "Anthropic")
    assert d2.vocab == ("Anthropic",)
    d3 = quick_add(p, "Claude")
    assert d3.vocab == ("Anthropic", "Claude")


def test_quick_add_rejects_empty(tmp_path) -> None:
    with pytest.raises(DictionaryError):
        quick_add(tmp_path / "d.toml", "   ")


# --- correction learning (add_replacement) -----------------------------------


def test_add_replacement_single_word(tmp_path) -> None:
    path = tmp_path / "dictionary.toml"
    d = add_replacement(path, "gonna", "going to")
    assert ("gonna", "going to") in d.words
    # persisted and applied by the engine
    assert ReplacementEngine(load(path)).apply("i am gonna go") == "i am going to go"


def test_add_replacement_multiword_is_phrase(tmp_path) -> None:
    path = tmp_path / "dictionary.toml"
    d = add_replacement(path, "my sequel", "MySQL")
    assert ("my sequel", "MySQL") in d.phrases
    assert d.words == ()
    assert ReplacementEngine(load(path)).apply("i use my sequel daily") == "i use MySQL daily"


def test_add_replacement_updates_existing(tmp_path) -> None:
    path = tmp_path / "dictionary.toml"
    add_replacement(path, "gonna", "going to")
    d = add_replacement(path, "gonna", "gunna")  # re-teach
    words = dict(d.words)
    assert words["gonna"] == "gunna"


def test_add_replacement_preserves_other_tiers(tmp_path) -> None:
    path = tmp_path / "dictionary.toml"
    path.write_text('vocab = ["Kubernetes"]\n[punctuation]\n"period" = "."\n', encoding="utf-8")
    d = add_replacement(path, "gonna", "going to")
    assert d.vocab == ("Kubernetes",)
    assert ("period", ".") in d.punctuation


def test_add_replacement_rejects_empty(tmp_path) -> None:
    with pytest.raises(DictionaryError):
        add_replacement(tmp_path / "d.toml", "   ", "x")


# --- ReplacementEngine (the layered ordering) --------------------------------


def test_phrase_replacement_case_insensitive() -> None:
    eng = ReplacementEngine(Dictionary(phrases=(("my sequel", "MySQL"),)))
    assert eng.apply("i love My Sequel databases") == "i love MySQL databases"


def test_phrases_longest_first() -> None:
    eng = ReplacementEngine(Dictionary(phrases=(("cube", "CUBE"), ("cube it all", "kubectl"))))
    # longer phrase wins even though "cube" is also a rule
    assert eng.apply("run cube it all now") == "run kubectl now"


def test_spoken_punctuation_removes_leading_space() -> None:
    eng = ReplacementEngine(Dictionary(punctuation=(("comma", ","), ("period", "."))))
    assert eng.apply("hello comma world period") == "hello, world."


def test_word_map_and_deletion() -> None:
    eng = ReplacementEngine(Dictionary(words=(("gonna", "going to"), ("basically", ""))))
    # "basically" deleted, "gonna" expanded, spaces tidied
    assert eng.apply("i am basically gonna go") == "i am going to go"


def test_layers_apply_in_order() -> None:
    d = Dictionary(
        phrases=(("my sequel", "MySQL"),),
        punctuation=(("period", "."),),
        words=(("um", ""),),
    )
    eng = ReplacementEngine(d)
    assert eng.apply("um my sequel is great period") == "MySQL is great."


def test_tidy_collapses_spaces_and_trims() -> None:
    eng = ReplacementEngine(Dictionary(words=(("uh", ""),)))
    assert eng.apply("  hello uh   there  ") == "hello there"


def test_empty_dictionary_is_identity() -> None:
    eng = ReplacementEngine(Dictionary())
    assert eng.apply("nothing changes here") == "nothing changes here"
