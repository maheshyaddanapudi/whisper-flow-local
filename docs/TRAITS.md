# Trait matrix: what to take from every prior-art project

Pass-2 research catalogued **256 implementation traits** across 12 projects — the six
open-source pipelines (VoiceInk, Handy, OpenWhispr, WhisperWriter, hyprvoice,
local-whisper), three minimal/CLI tools (nerd-dictation, BlahST, OpenSuperWhisper), one
batch app (Vibe), and two closed-source products (Superwhisper, Talon Voice).

**Philosophy: traits, not code.** We build an original app and adopt the best *design*
from each project. No forking, no code reuse — which also keeps us clean of the GPL-3
projects (VoiceInk, WhisperWriter, nerd-dictation) while our own license stays MIT.

## Best-approach matrix

| Category | Recommended approach for whisper-flow-local (source of the trait) |
|---|---|
| **Recording modes** | Default hotkey uses *hybrid* semantics: tap = toggle, hold ≥0.5 s = push-to-talk on the same binding (VoiceInk/Superwhisper). Add continuous mode — silence-endpointed utterances (~900 ms) that auto-rearm (WhisperWriter) — plus a ~150 ms min-duration discard for accidental taps, ~0.5 s release grace (nerd-dictation), and length-aware cancel: instant <30 s, confirm ≥30 s (Superwhisper). |
| **Hotkeys** | In-app pluggable listener (pynput default; evdev on Linux; Quartz event tap on macOS for bare-modifier keys like Right-Cmd). Two intents: hotkey A = raw transcribe, hotkey B = transcribe + Ollama cleanup (Handy). Also expose IPC/CLI verbs so tiling-WM users bind compositor keys instead (hyprvoice) — the only reliable path on strict Wayland. |
| **Audio capture** | `sounddevice` at 16 kHz mono (Whisper-native, no resample) into an in-memory ring buffer with ~0.5–1 s chunks; explicit device picker; audible start/stop cues; audio stays in RAM unless history is enabled (BlahST); optional media auto-pause (VoiceInk/OpenWhispr) and a 5-minute max-recording safety cap (hyprvoice). |
| **VAD** | Two layers, default-on (WhisperWriter/Handy): cheap RMS/webrtcvad endpointing for auto-stop, plus Silero VAD (`vad_filter=True` in faster-whisper) to scrub audio and kill silence hallucinations. Half the field ships no VAD — easy quality win. |
| **STT engines** | Thin `STTBackend` interface: faster-whisper default (temperature 0, VAD on, `condition_on_previous_text=False`), whisper.cpp on macOS for Metal/CoreML. Model stays resident in the daemon (BlahST server pattern) with configurable unload timeout (Handy). Interface leaves room for streaming/Parakeet backends. |
| **Model management** | Curated picker with size + speed/accuracy ratings and exactly one Recommended default (Superwhisper/Vibe); auto-discovery of dropped model files (Handy); and `whisper-flow bench --audio clip.wav` that times every installed model on the user's hardware (hyprvoice's test-models). |
| **LLM post-processing** | Ollama first-class and default-available — nobody in the field does this. Boolean goals (punctuation / grammar / fillers / stutters) compiled into a short plain-text prompt tuned for 4–8B models — no XML tags (Superwhisper's own caveat). ~50-char minimum gate (local-whisper), raw + cleaned both kept (VoiceInk), `keep_alive` so the model stays warm, default gemma3:4b-class with a warning below ~3B. |
| **Dictionary/replacements** | Two tiers (Superwhisper): ≤~20 vocabulary hints in Whisper's `initial_prompt` (more degrades STT) + deterministic post-STT replacement engine ordered per nerd-dictation (multi-word regex → spoken-punctuation map → case-insensitive word map where `""` deletes fillers). Plain TOML/CSV files (Talon: diffable/syncable) + quick-add hotkey (VoiceInk). Runs BEFORE the LLM so deterministic fixes survive regardless of cleanup. |
| **Text injection** | `Injector` interface with ordered, user-configurable per-platform chain (hyprvoice): clipboard-paste with full snapshot/restore and layout-aware paste keycode (OpenSuperWhisper) → char-typing with tunable delay → copy-only. Terminal variants (Ctrl+Shift+V / Shift+Insert), Auto-Submit and trailing-space opt-ins (Handy), never-press-Enter default (nerd-dictation). Detect available Linux tools at startup and report which backend is active. |
| **Context awareness** | Frontmost-app detection at record-START (fixes Superwhisper's after-STT timing bug) driving per-app profiles: terminals/editors suppress auto-capitalization (local-whisper), declarative match rules (Talon) select prompt + replacements + injection method. Selected-text/clipboard context opt-in per profile; log exactly what was sent to the LLM (Superwhisper). No screen capture in v1. |
| **UI/UX** | Tray/menu-bar residency + small always-on-top overlay with three distinct states (recording / transcribing / cleaning), positionable or disableable; audio cues for eyes-free PTT; recent-dictations re-paste list (local-whisper) with retention limits (Handy); Escape-cancel with double-press confirm (VoiceInk); libnotify alternative on Linux; headless `--no-ui` mode. |
| **Config** | One schema-driven TOML (`~/.config/whisper-flow/config.toml`): every option carries type/default/options/description in a single schema module that generates CLI help, settings UI, and docs (WhisperWriter's zero-drift trick). Hot-reload with session-boundary semantics (hyprvoice). Config version field from day one. |
| **Architecture/IPC** | Long-lived daemon owning the models, structured as an explicit named state machine with abort paths: `idle → recording → transcribing → cleaning → injecting` (hyprvoice). Unix-socket/named-pipe IPC verbs (`toggle`, `ptt-down`, `ptt-up`, `cancel`, `status`, `paste-last`, `paste-last-raw`) + thin CLI wrapper — solves Wayland hotkeys, scripting, and launcher integrations at once. Single instance via socket ownership, never pkill. |
| **Privacy** | Strict 100%-local guarantee as the headline: no cloud code paths at all, zero telemetry, audio in RAM and discarded by default, documented data-flow statement listing every file written. Every commercial competitor hedges — an absolute claim is simpler to build and a real edge. |
| **Packaging** | pipx/uv-installable PyPI package as the floor (`uvx whisper-flow-local`), then brew / AUR + systemd user unit / winget; bundles later. Auto-download the small default model on first run → install-to-speaking in under two minutes; print a dependency report (which injection/hotkey backends found) at first launch. |

## Standout tricks to adopt (project-attributed)

1. Hybrid tap-vs-hold hotkey with 0.5 s discriminator — VoiceInk/Superwhisper
2. Continuous mode: silence-endpointed, auto-rearming utterances — WhisperWriter
3. Two-layer VAD (endpointing + Silero scrub) — WhisperWriter/Handy
4. Second hotkey for raw-vs-cleaned per utterance — Handy
5. Paste-last-raw vs paste-last-enhanced + retry-with-last-audio — VoiceInk
6. Boolean cleanup goals compiled into one prompt — hyprvoice (pointed at Ollama)
7. 50-char LLM gate — local-whisper
8. Two-tier dictionary + layered replacement ordering — Superwhisper + nerd-dictation
9. Quick-add-to-dictionary hotkey — VoiceInk
10. Injection fallback chain with per-backend timeouts — hyprvoice + Handy
11. Clipboard snapshot/restore + layout-aware keycodes — OpenSuperWhisper/Talon
12. Never-simulate-Enter default; Auto-Submit opt-in — nerd-dictation + Handy
13. Model-resident daemon + configurable unload; Ollama keep_alive — BlahST + Handy
14. Socket IPC verbs + CLI wrapper — hyprvoice + Handy
15. Named state machine with abort paths — hyprvoice
16. Schema-driven config generating UI/CLI/docs — WhisperWriter
17. On-device model benchmark command — hyprvoice
18. Curated model picker w/ one Recommended — Superwhisper + Vibe
19. Record-start app detection → per-app profiles — local-whisper + Talon + VoiceInk
20. What-was-sent-to-the-LLM transparency log — Superwhisper
21. Length-aware cancel confirmation — Superwhisper + VoiceInk
22. Recent-dictations re-paste menu — local-whisper + Handy
23. Media auto-pause during recording — VoiceInk/OpenWhispr
24. Audio kept in RAM by default — BlahST
25. Tray + overlay with distinct pipeline states — Handy + OpenSuperWhisper

## Pitfalls observed in prior art (avoid)

- **No VAD at all** (VoiceInk, OpenWhispr, Superwhisper, hyprvoice, OpenSuperWhisper) —
  the most common defect in the field; silence hallucinations follow.
- Local-LLM cleanup as a cloud-first afterthought (Handy) or cloud-only (hyprvoice).
- Blind fixed sleeps in the paste path (60 ms delays, 0.1 s clipboard-restore races) —
  verify clipboard ownership/content instead.
- Char-typing that garbles non-QWERTY layouts — resolve keycodes from the active layout.
- Stopping recording via `pkill` by process name (BlahST) — racy; use socket IPC.
- Amplitude-only silence detection as the *only* VAD — fails in noisy rooms.
- `condition_on_previous_text=True` — propagates hallucinations across utterances.
- XML-tagged/long prompts for cleanup — small local models misinterpret them
  (Superwhisper's own docs admit this).
- Unbounded vocabulary hints degrading STT — cap `initial_prompt`, push the rest to
  deterministic replacements.
- Config fragmentation / flat-key drift / CLI-flags-only — one schema-versioned file.
- Source-only onboarding walls ("clone, venv, manual CUDA") — package properly,
  auto-download a small default model.
- Feature creep before the core loop is solid (accounts, notes, meetings, 7 export
  formats, assistant chat).
- Cloud tiers/analytics diluting the privacy headline — zero telemetry, no cloud paths.
- Zero recording feedback — the user must always see/hear the mic is hot.
- Injection with no recovery when focus is wrong — copy-only fallback + re-paste history.
- Capturing app context AFTER transcription — window may have switched; capture at
  record-start.
- Monolithic cores that make contributions require rewrites (WhisperWriter's LLM layer
  died in an unmerged PR) — keep backend seams clean.
- External-binary zoos with no detection/guidance — detect at startup, always have a
  clipboard fallback.
- API keys in plaintext config — OS keyring if any secret ever exists.
- GPL-3 code reuse — traits only; our code stays original and MIT.

## Gaps nobody fills (our differentiation)

1. **Ollama cleanup as a first-class default** — on by default, prompt-engineered for
   4–8B models, latency-gated. No project ships this. It is whisper-flow-local's
   core identity.
2. **Per-app tone/formatting profiles cross-platform** — only mac-only/closed tools do
   it; nobody does it in one cross-platform app.
3. **Streaming partial-transcript preview** — tiny-model live preview + big-model final;
   only hobby-grade attempts exist.
4. **Learning from user corrections** — Wispr's signature "never the same mistake twice"
   loop is completely unreplicated: watch post-injection edits / accept corrections and
   feed them back into vocabulary, replacements, and few-shot prompt examples.
5. **True cross-platform parity in one runtime** — every prior project is single-OS or
   asymmetric; equal hybrid-hotkey/PTT/injection on macOS + Windows + Linux is unclaimed.
6. **Verified injection** — confirm text actually landed (focus check at paste time,
   clipboard-ownership verification, buffer-on-focus-loss) instead of blind sleeps.
7. **Safe hands-free continuous mode** — VAD-endpointed auto-rearm + Silero gating +
   per-utterance cleanup + live indicator; only abandoned WhisperWriter comes close.
8. **Local voice-driven editing** — select text, hold hotkey, say "make this formal";
   selection becomes the LLM input. Natural extension of our pipeline; nobody does it
   locally.
9. **Hardware-grounded model guidance** — onboarding benchmark of 2–3 models on the
   user's machine with measured latency, recommending one.
10. **Verifiable privacy UX** — what-was-sent log + no-network guarantee + auditable
    list of files the app writes.
