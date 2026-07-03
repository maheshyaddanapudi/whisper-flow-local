# Research: How Wispr Flow works, and how to rebuild it locally

Deep-research findings for the `whisper-flow-local` project: recreate Wispr Flow's
core dictation experience fully offline, with a Whisper-family STT engine plus an
Ollama-hosted LLM for transcript cleanup.

**Method & confidence note.** Findings come from a multi-agent research pass over 22
sources (Wispr's own engineering blog, privacy policy and docs, Wikipedia, third-party
reviews, and the READMEs/PRs of 8 open-source alternatives). Every claim below is backed
by a direct quote from the cited source. An adversarial verification pass confirmed the
latency-budget claim (3-0 votes) and refuted one overreach (noted below); the remaining
claims were extracted with quotes but not independently re-verified, so treat specific
benchmark numbers as directional.

---

## 1. What Wispr Flow actually is

- **Product**: system-wide AI dictation. Hold a global hotkey, speak, release — polished
  text appears at the cursor in whatever app has focus. macOS, Windows (Electron), iOS
  (third-party keyboard), and Android. No Linux support. [4][19][6]
- **Auto-editing**: filler-word removal ("um, uh, like"), automatic punctuation and
  formatting, context-aware tone per application (casual for Slack, professional for
  email), Command Mode for natural-language edits ("make this formal", "turn into bullet
  points"), Whisper Mode for quiet environments, 100+ languages with code-switching,
  personal dictionary that learns user vocabulary. [6][19][4]
- **Pricing (2026)**: free tier capped at 2,000 words/week; Pro $15/month ($144/yr);
  Enterprise $24/user/month. [6][12]
- **Resource footprint**: users report ~800 MB RAM and ~8% CPU while *idle* on a 2021
  MacBook Pro — a bar a lean local clone can easily beat. [6][12]
- **Company**: Wispr, founded 2021 (Tanay Kothari, Sahaj Garg), pivoted from neural
  wearables to the Flow software in 2024; ~$81M raised; ~1B words dictated/month as of
  Sep 2025. [4][1]

## 2. Its architecture — and why a clone must substitute every stage

- **Transcription is cloud-only.** Wispr's own docs: "Transcription always happens in
  the cloud to provide the best speed and accuracy." There is no offline mode, even with
  Privacy Mode enabled; a constant internet connection is required. [2][3][12][13]
- **Third-party AI providers process the audio** under zero-data-retention agreements —
  Wispr does not run its ASR/LLM stack exclusively in-house. Even with Cloud Sync
  disabled, raw transcripts may still be uploaded because core dictation depends on the
  cloud. Zero data retention is an *opt-in* configuration (Privacy Mode on + Cloud Sync
  off), not the default. [3][2]
- **Pipeline shape** (from Wispr's engineering blog): ASR → personalized LLM formatting.
  "Personalized LLMs with token level formatting control" handle preferences like dash
  vs. comma style and capitalization. The data model distinguishes three artifacts:
  audio, transcripts, and *edits* — i.e., the LLM cleanup step is a first-class stage,
  which is exactly the stage we'll map onto Ollama. [1][2]
  - One nuance from verification: the claim that Wispr *already ships* fully custom
    context-conditioned ASR was **refuted** (2-1) — the blog says they are *building*
    context-conditioned models; the shipped product leans on third-party providers. [1][3]
- **Latency budget (verified 3-0)**: "E2E ASR inference in <200ms, E2E LLM inference in
  <200ms, and maximum networking budget of 200ms" — formatted text within **~700 ms** of
  end of speech. That's the bar. A local clone gets the 200 ms network budget back for
  free and can realistically land at ~1–1.5 s, which existing local clones confirm is
  perfectly usable. [1][17]
- **Context awareness has a privacy cost**: reviews report the app captures screenshots
  of the active window every few seconds and can read keystrokes — features a local
  clone can offer opt-in without any data ever leaving the machine. [6][4]

## 3. Local STT engine options

| Engine | Strengths | Caveats |
|---|---|---|
| **whisper.cpp** (GGML) | Dependency-free C/C++; Metal/CoreML on Apple Silicon, CUDA, Vulkan, AVX, OpenVINO; 4-bit quantization; streaming examples + VAD in-repo; MIT | Best all-round choice for cross-platform push-to-talk [11][6b] |
| **faster-whisper** (CTranslate2) | Excellent on NVIDIA GPU (13-min file in ~16 s with INT8 batching on RTX 3070 Ti) and solid on x86 CPU (large-v3-turbo ~8–12× real-time with INT8); easy Python API; built-in Silero VAD flag | CPU-only on Macs — ~6.96 s vs ~0.19–1.2 s for CoreML/MLX paths in the mac-whisper-speedtest benchmark (~35× slower than the fastest) [7][9][11] |
| **Parakeet (NVIDIA TDT)** | Non-autoregressive → very fast: ~1.69% WER at 110–300× real-time on Apple Silicon via FluidAudio/CoreML (~66 MB RAM on the Neural Engine); parakeet.cpp has true streaming variants (80–1,120 ms configurable) | English-only (110M) or ~25 European languages (600M v3); far smaller ecosystem than Whisper; CC-BY-4.0 [10][12b][8] |
| **whisper-large-v3-turbo** | ~2.1% WER English, 99 languages, MIT; the accuracy gap vs Parakeet on clean English is marginal | Autoregressive → slower than Parakeet on the same hardware [9][8] |

Other relevant facts:
- Naive (unoptimized) Whisper large-v3 runs ~1× real-time on an M1 — optimized runtimes
  are mandatory, not optional. [10]
- **VAD is the standard hallucination fix**: silence/noise is the leading cause of
  hallucinated transcripts; Silero VAD is integrated as a flag in faster-whisper and
  available in whisper.cpp. [11]
- For English dictation, `small.en` / `base.en` / distil models save ~70% latency vs the
  largest models with little practical accuracy loss for short utterances. [11]

**Conclusion**: pluggable STT backends. Default `faster-whisper` (small.en) on
Windows/Linux (great on CUDA and fine on CPU), `whisper.cpp` (Metal/CoreML) on macOS,
Parakeet as a fast English-only option later.

## 4. The Ollama cleanup stage (proven pattern)

Multiple working projects already implement exactly our target pipeline:

- **Murmur** (blog write-up of a working Wispr Flow replacement): faster-whisper
  `small.en` (0.3–0.5 s/sentence on GPU) + **Ollama `qwen2.5:7b`** cleanup (~1 s once
  warm) doing filler removal, punctuation, capitalization, and self-interruption
  correction. End-to-end ~1.5 s from key release on an RTX 3060. Remaining gaps vs Wispr
  Flow: streaming-while-speaking and per-app tone matching. [17]
- **WhisperWriter PR #102**: two LLM modes worth copying — **cleanup mode** (fixed system
  prompt for grammar/style) and **instruction mode** (user-defined transformation), plus
  a find-and-replace layer (TXT pairs or JSON regex with capture groups) as a
  personal-dictionary mechanism. (PR unmerged; upstream is effectively unmaintained —
  a pattern to borrow, not a base to build on.) [14][22]
- **local-whisper** (macOS): Ollama refinement pass that fixes punctuation, removes
  fillers, formats lists — but **only for transcripts longer than 50 characters**, a
  smart latency guard for short utterances. [15]
- **Hyprvoice** (Linux/Wayland, Go): optional LLM post-processing plus custom prompts and
  keywords sent to both the LLM and the STT model — a personal-dictionary mechanism that
  improves both stages at once. [16]

Model candidates for the cleanup pass: `qwen2.5:7b` (proven in Murmur), `llama3.2:3b` /
`gemma3:4b` / `phi-4-mini` for lower latency on weaker hardware. Keep the model warm via
Ollama `keep_alive`; cleanup latency ~1 s warm on mid-range GPUs. [17]

## 5. System integration (hotkey, audio, text injection)

- **Global hotkey**: `pynput` works for hotkey capture + paste simulation on
  Windows/macOS/Linux-X11 (Murmur, WhisperWriter). Rust alternative: `rdev` (Handy).
  Hold-to-talk vs toggle: WhisperWriter implements four recording modes (continuous,
  VAD-stop, press-to-toggle, hold-to-record) — a good reference design. On Wayland,
  compositor-level keybindings (e.g. Hyprland `bind`/`bindr`, release-fired) sidestep
  the global-hotkey problem entirely. [17][22][13b][16]
- **Text injection** (the platform-splintered part):
  - macOS: clipboard paste (Cmd+V) or simulated keystrokes — both proven (local-whisper,
    VoiceInk). Requires Accessibility permission. [15][20]
  - Windows: `pynput` Ctrl+V paste simulation is sufficient (Murmur). [17]
  - Linux X11: `xdotool` — but it's X11-only and slow for non-English characters. [18]
  - Linux Wayland: `wtype`, falling back to `ydotool` (kernel-level via `/dev/uinput`;
    needs the `ydotoold` daemon, `input` group membership, and a udev rule), falling
    back to clipboard paste. Hyprvoice's **fallback chain with clipboard restore**
    (preserve the user's prior clipboard) is the design to copy. [18][16]
  - nerd-dictation's `--simulate-input-tool=` pluggable-backend pattern is the right
    abstraction. [18]
- **Audio**: 16 kHz mono capture via `sounddevice`/`cpal`; Silero VAD for auto-stop
  after ~1–3 s of silence (local-whisper auto-stops after ~3 s). [13b][15]

## 6. Prior art worth studying (and what each proves)

| Project | Stack | Takeaway |
|---|---|---|
| **VoiceInk** (GPL-3, ~5.4k★) | Swift + whisper.cpp + FluidAudio/Parakeet, macOS | The strongest OSS Wispr Flow alternative; 100% offline; push-to-talk + personal dictionary [20] |
| **Handy** (MIT) | Tauri: React/TS + Rust (`cpal`, `rdev`, `vad-rs`/Silero, `rubato`); whisper GGML + Parakeet V3 | Best cross-platform reference architecture; actively maintained (v0.9.0, Jul 2026) [13b] |
| **OpenWhispr** (MIT) | Electron/TS + whisper.cpp + sherpa-onnx (Parakeet), SQLite | Cross-platform local dictation + "agent mode" with custom system prompts [21][19] |
| **Hyprvoice** | Go daemon, PipeWire, Unix-socket IPC, state machine idle→recording→transcribing→LLM→injecting | Cleanest pipeline architecture; Wayland injection fallback chain [16] |
| **WhisperWriter** (GPL-3, ~1.1k★) | Python/PyQt5 + faster-whisper + pynput | Proves the whole pipeline works in pure Python; 4 recording modes; lightly maintained [22] |
| **local-whisper** | Hammerspoon + whisper.cpp + Ollama, macOS | Minimal hold-key → whisper.cpp → Ollama → paste loop; two-tier model trick (tiny for live preview, medium for final) [15] |
| **Murmur** | Python: faster-whisper + Ollama qwen2.5:7b + pynput + pystray | Closest to our exact target; concrete latency numbers [17] |

**License note**: whisper.cpp and faster-whisper are MIT; Parakeet models CC-BY-4.0;
Handy MIT; VoiceInk/WhisperWriter GPL-3 (study, don't copy code unless we accept GPL).

## 7. Feature → local mechanism map

| Wispr Flow feature | Local equivalent | Confidence |
|---|---|---|
| Push-to-talk global hotkey | pynput/rdev hold-or-toggle | Proven ×5 projects |
| Types into any app | Clipboard-paste w/ restore + keystroke fallback | Proven, per-OS quirks |
| Filler removal, punctuation, formatting | Ollama cleanup prompt (qwen2.5:7b class) | Proven (Murmur, local-whisper, Hyprvoice) |
| Personal dictionary | Regex/text replace + keyword hints injected into STT `initial_prompt` and LLM prompt | Proven pattern (WW PR#102, Hyprvoice) |
| Tone per application | Active-window detection → per-app prompt profile | Feasible, not yet proven in OSS |
| Command mode ("make this formal") | Instruction-mode prompt against selected text | Pattern exists (WW PR#102, OpenWhispr agent mode) |
| ~700 ms E2E latency | ~1–1.5 s locally on decent hardware | Verified bar [1]; local numbers from [17] |
| Streaming-while-speaking | Hard locally; Phase-2+ (two-tier models / parakeet.cpp streaming) | Open challenge |

---

## Sources

1. https://wisprflow.ai/post/technical-challenges — Wispr engineering blog (Sahaj Garg, Sep 2025) *(primary)*
2. https://wisprflow.ai/privacy *(primary)*
3. https://docs.wisprflow.ai/articles/6274675613-privacy-mode-data-retention *(primary)*
4. https://en.wikipedia.org/wiki/Wispr_Flow
5. https://www.getvoibe.com/resources/wispr-flow-review/
6. https://weesperneonflow.ai/en/blog/2026-02-09-wispr-flow-review-cloud-dictation-2026/
7. https://github.com/anvanvan/mac-whisper-speedtest *(primary)*
8. https://dicta.to/blog/whisper-vs-parakeet-vs-apple-speech-engine/
9. https://www.arunbaby.com/speech-tech/0073-whisper-vs-parakeet-asr-decision/
10. https://macparakeet.com/blog/whisper-to-parakeet-neural-engine/
11. https://builderai.tools/blog/whisper-cpp-vs-whisper-speed-and-accuracy
12. https://modelslab.com/blog/audio-generation/parakeet-cpp-vs-whisper-self-hosted-asr-comparison-2026 *(12b)*
13. https://everydayaiwithbrian.com/blog/replace-wispr-flow.html — Murmur write-up *(also cited as 17)*
14. https://github.com/savbell/whisper-writer/pull/102 *(primary)*
15. https://github.com/luisalima/local-whisper *(primary)*
16. https://github.com/LeonardoTrapani/hyprvoice *(primary)*
17. https://everydayaiwithbrian.com/blog/replace-wispr-flow.html — Murmur
18. https://github.com/ideasman42/nerd-dictation/blob/main/readme-ydotool.rst *(primary)*
19. https://openwhispr.com/compare/wisprflow
20. https://github.com/beingpax/VoiceInk *(primary)*
21. https://github.com/OpenWhispr/openwhispr *(primary)*
22. https://github.com/savbell/whisper-writer *(primary)*
13b. https://github.com/cjpais/Handy *(primary)*
6b. https://builderai.tools/blog/whisper-cpp-vs-whisper-speed-and-accuracy
