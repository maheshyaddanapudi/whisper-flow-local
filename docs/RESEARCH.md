# Research: How Wispr Flow works, and how to rebuild it locally

Verified deep-research findings for `whisper-flow-local`: recreate Wispr Flow's core
dictation experience fully offline — Whisper-family STT plus an Ollama-hosted LLM for
transcript cleanup.

**Method & confidence.** Two multi-agent research passes:

- **Pass 1 (verification)**: 5 search angles → 22 sources fetched → 110 claims extracted
  with direct quotes → the top 25 claims each adversarially verified by 3 independent
  skeptic agents. Result: **22 confirmed, 3 refuted, 0 unverified**, merged into the 8
  findings below. Every finding carries its vote and confidence.
- **Pass 2 (trait extraction)**: 12 parallel agents catalogued 256 implementation traits
  from every notable Wispr Flow alternative (open-source and closed). See
  [TRAITS.md](TRAITS.md) for the full matrix.

Refuted claims are listed at the end — details that sounded right but failed
verification, kept so we don't reintroduce them.

---

## Verified findings

### 1. Wispr Flow transcribes only in the cloud — always *(high confidence, 3-0, ×3 claims)*

Transcription never happens on-device, regardless of Privacy Mode or any setting.
Privacy Mode / Cloud Sync toggles control data *retention*, not processing *location*.
First-party sources say it verbatim: "Transcription always happens in the cloud to
provide the best speed and accuracy" (privacy page), "Transcription always occurs on
the cloud" (data-controls page), and the engineering blog describes "cloud based speech
processing infrastructure for 1B users." A fully local clone is therefore a genuine
architectural departure — and its entire privacy story is a differentiator Wispr
structurally cannot match. [S1][S2][S3][S4]

### 2. The pipeline is two-stage: ASR → LLM formatting, with a 700 ms budget *(high, 3-0, ×2)*

From Wispr's own engineering blog: "full transcription and LLM formatting/interpretation
of their speech within 700ms of when they stop speaking," budgeted as "E2E ASR inference
in <200ms, E2E LLM inference in <200ms, and a maximum networking budget of 200ms."
A Baseten case study independently confirms production use of **fine-tuned Llama models
for transcript enhancement** at under 700 ms p99. This validates our exact architecture:
Whisper STT + Ollama-hosted LLM cleanup is the same two-stage shape, run on-device.
700 ms is the latency bar; local clones prove ~1–1.5 s feels fine. [S1][S5]

### 3. Wispr depends on third-party AI providers *(medium confidence, 2-1)*

Dictation data is processed by third-party AI providers (historically including OpenAI)
under zero-data-retention agreements — "a combination of open-source models and
proprietary LLM providers." Not solely in-house models. Note: it is **not** publicly
confirmed that Wispr uses Whisper-family ASR specifically, and ZDR agreements are
contractual assertions, not independently auditable. [S3][S4][S6]

### 4. A fully local clone is proven feasible — six live projects ship the pipeline *(high, 3-0, ×6)*

At least six active open-source projects ship hotkey → record → local STT →
type-into-focused-app with no cloud dependency: **Handy** (MIT, cross-platform,
Tauri/Rust), **VoiceInk** (GPL-3, native macOS Swift + whisper.cpp, ~5.4k stars),
**OpenWhispr** (MIT, ~4.2k stars, "the open-source and free alternative to WisprFlow"),
**WhisperWriter** (Python + faster-whisper + pynput), **hyprvoice** (Go, Linux
Wayland), and **local-whisper** (macOS, hold-Right-Cmd via whisper.cpp). All verified
live in 2026 with the claimed architectures. [S7]–[S12]

### 5. The STT → local-LLM cleanup stage exists in the wild, with concrete model choices *(high, 3-0, ×4)*

- **local-whisper**: Ollama cleanup with **gemma3:4b default** — fixes punctuation,
  removes fillers, formats lists — and only runs on transcripts **longer than 50
  characters** (latency guard). [S10]
- **WhisperWriter PR #102**: two hotkey-activated modes — *cleanup* and *instruction* —
  with recommended Ollama models `airat/karen-the-editor-v2-strict` (cleanup) and
  `llama3.2` (instruction). [S13]
- **OpenWhispr**: llama.cpp for fully local LLM text processing. [S9]
- **hyprvoice**: optional LLM grammar/punctuation stage between STT and injection
  (cloud-API-based — the gap we close by making it Ollama-native). [S11]

### 6. Handy provides a verified system-integration blueprint *(high, 3-0, ×2)*

Tauri v2, React/TS frontend, Rust backend: `cpal` (audio capture), Silero VAD via
`vad-rs`, `rdev` (global hotkeys), `rubato` (resampling). Injection: xdotool on X11,
wtype/dotool on Wayland, clipboard paste, `enigo` fallback. Wayland global hotkeys
require desktop-environment keybinds or CLI flags (`--toggle-transcription`) — the
pattern we generalize into a daemon + IPC verbs. Verified against both README and
`Cargo.toml`. [S7]

### 7. Practical local model menu is well-established *(high, 3-0, ×2)*

Whisper GGML/GGUF: Small 487 MB, Medium-q4 492 MB, large-v3-turbo 1.6 GB, Large-q5
1.1 GB. **NVIDIA Parakeet TDT 0.6B v3** (478 MB int8, via sherpa-onnx/transcribe-rs)
runs CPU-only at ~5× real-time on mid-range hardware with automatic language detection
(developer benchmark). Handy and OpenWhispr both ship this dual Whisper+Parakeet
setup. [S7][S9]

### 8. Wispr's differentiating UX features have all been replicated locally *(high, 3-0)*

VoiceInk demonstrates — in verifiable GPL-3 source, not marketing — configurable
push-to-talk with toggle/PTT/hybrid modes (`RecordingShortcutManager.swift`), a personal
dictionary fed into the enhancement prompt (`DictionaryService.swift`), per-app
detection via bundle-ID trigger templates, screen-content context injection
(`ScreenCaptureService` → `<CURRENT_WINDOW_CONTEXT>`), and an `OllamaService`
defaulting to `localhost:11434`. macOS-only and GPL — we adopt the traits, not the
code. [S8]

---

## Supporting research (source-quoted, not individually 3-vote verified)

### STT engine performance (directional numbers)

- Apple Silicon (mac-whisper-speedtest, M4/24 GB, large models): FluidAudio-CoreML
  (Parakeet) ~0.19 s, Parakeet-MLX ~0.50 s, mlx-whisper ~1.02 s, whisper.cpp ~1.23 s,
  **faster-whisper ~6.96 s (CPU-only on Macs — ~35× slower than the leader)**. Hence
  the macOS backend must be whisper.cpp (Metal/CoreML) or MLX, never CTranslate2. [S14]
- CPU (x86): whisper-large-v3-turbo with faster-whisper INT8 ≈ 8–12× real-time — a GPU
  is not strictly required. [S15]
- NVIDIA GPU: faster-whisper INT8+batching transcribes 13 min of audio in ~16 s
  (RTX 3070 Ti). [S16]
- Unoptimized Whisper large-v3 on an M1 ran ~1× real-time — optimized runtimes are
  mandatory. [S17]
- Whisper hallucinates on silence/noise; Silero VAD (one flag in faster-whisper) is the
  standard mitigation. [S16]
- English accuracy: large-v3-turbo ~2.1% WER vs Parakeet ~1.7–3-4% depending on source —
  marginal for dictation; choose by speed and language needs. [S15][S18]

### A working reference of our exact target (Murmur)

faster-whisper `small.en` (0.3–0.5 s/sentence on GPU) + Ollama `qwen2.5:7b` (~1 s warm)
→ ~1.5 s end-to-end from key release on an RTX 3060, using pynput for hotkey + paste and
pystray for the tray. Its author's remaining envy of Wispr Flow: streaming-while-
speaking and per-app tone. [S19]

### Linux injection facts

xdotool is X11-only and slow for non-English characters; ydotool works on Wayland by
simulating input at the kernel level via `/dev/uinput` but needs the `ydotoold` daemon,
`input` group membership, and a udev rule. [S20]

---

## Refuted claims (do not reuse)

1. ~~"Wispr builds its own context-conditioned ASR rather than off-the-shelf"~~ — the
   blog says they are *building* such models; the shipped product relies on third-party
   providers (1-2).
2. ~~"hyprvoice injects via wtype primary → ydotool → clipboard-restore chain"~~ —
   misstated; its actual mechanism/order differs (0-3). We specify our own configurable
   chain rather than citing hyprvoice's order.
3. ~~"VoiceInk achieves roughly 99% accuracy with near-instant local transcription"~~ —
   marketing-derived numbers, not verified (1-2).
4. ~~"hyprvoice is a batch record-then-transcribe design"~~ — its pipeline
   architecture claim as originally worded failed verification (1-2).

---

## Sources

- [S1] https://wisprflow.ai/post/technical-challenges (primary, Sep 2025)
- [S2] https://wisprflow.ai/privacy (primary)
- [S3] https://docs.wisprflow.ai/articles/6274675613-privacy-mode-data-retention (primary)
- [S4] https://wisprflow.ai/data-controls (primary)
- [S5] https://www.baseten.co/resources/customers/wispr-flow/
- [S6] https://docs.wisprflow.ai/articles/3467817258-security-and-compliance-faq (primary)
- [S7] https://github.com/cjpais/Handy (primary)
- [S8] https://github.com/beingpax/VoiceInk (primary)
- [S9] https://github.com/OpenWhispr/openwhispr (primary)
- [S10] https://github.com/luisalima/local-whisper (primary)
- [S11] https://github.com/LeonardoTrapani/hyprvoice (primary)
- [S12] https://github.com/savbell/whisper-writer (primary)
- [S13] https://github.com/savbell/whisper-writer/pull/102 (primary)
- [S14] https://github.com/anvanvan/mac-whisper-speedtest (primary)
- [S15] https://www.arunbaby.com/speech-tech/0073-whisper-vs-parakeet-asr-decision/
- [S16] https://builderai.tools/blog/whisper-cpp-vs-whisper-speed-and-accuracy
- [S17] https://macparakeet.com/blog/whisper-to-parakeet-neural-engine/
- [S18] https://dicta.to/blog/whisper-vs-parakeet-vs-apple-speech-engine/
- [S19] https://everydayaiwithbrian.com/blog/replace-wispr-flow.html (Murmur)
- [S20] https://github.com/ideasman42/nerd-dictation/blob/main/readme-ydotool.rst (primary)

Additional product-trait sources (pass 2): https://superwhisper.com, https://talonvoice.com,
https://github.com/QuantiusBenignus/BlahST, https://github.com/Starmel/OpenSuperWhisper,
https://github.com/thewh1teagle/vibe, https://en.wikipedia.org/wiki/Wispr_Flow.
