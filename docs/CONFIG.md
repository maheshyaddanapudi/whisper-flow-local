# Configuration reference

_Generated from the config schema — do not edit by hand._

Settings live in `~/.config/whisper-flow/config.toml`. Any option can be
overridden by an environment variable named `WHISPER_FLOW_<SECTION>_<NAME>`
(e.g. `cleanup.model` -> `WHISPER_FLOW_CLEANUP_MODEL`). Precedence:
environment variable > config file > default.

| Key | Env var | Type | Default | Choices | Description |
| --- | --- | --- | --- | --- | --- |
| `general.language` | `WHISPER_FLOW_GENERAL_LANGUAGE` | str | `"auto"` |  | Spoken language hint for STT ('auto' to detect). |
| `general.max_recording_seconds` | `WHISPER_FLOW_GENERAL_MAX_RECORDING_SECONDS` | int | `300` |  | Hard safety cap on a single recording. |
| `hotkey.primary` | `WHISPER_FLOW_HOTKEY_PRIMARY` | str | `"ctrl+shift+space"` |  | Global hotkey for dictation (tap = toggle, hold = push-to-talk). |
| `hotkey.mode` | `WHISPER_FLOW_HOTKEY_MODE` | str | `"hybrid"` | hybrid, toggle, push_to_talk, continuous | Recording mode for the primary hotkey. |
| `hotkey.hold_threshold_ms` | `WHISPER_FLOW_HOTKEY_HOLD_THRESHOLD_MS` | int | `500` |  | Hold longer than this to act as push-to-talk; shorter is a toggle tap. |
| `hotkey.min_duration_ms` | `WHISPER_FLOW_HOTKEY_MIN_DURATION_MS` | int | `150` |  | Recordings shorter than this are discarded as accidental taps. |
| `hotkey.release_grace_ms` | `WHISPER_FLOW_HOTKEY_RELEASE_GRACE_MS` | int | `500` |  | Grace period after PTT key release before stopping capture. |
| `hotkey.backend` | `WHISPER_FLOW_HOTKEY_BACKEND` | str | `"auto"` | auto, pynput, evdev, quartz, none | Hotkey listener backend. |
| `audio.sample_rate` | `WHISPER_FLOW_AUDIO_SAMPLE_RATE` | int | `16000` | 8000, 16000, 22050, 44100, 48000 | Capture sample rate in Hz (Whisper-native is 16000). |
| `audio.device` | `WHISPER_FLOW_AUDIO_DEVICE` | str | `""` |  | Input device name substring; empty uses the system default. |
| `audio.chunk_ms` | `WHISPER_FLOW_AUDIO_CHUNK_MS` | int | `500` |  | Audio capture chunk size in milliseconds. |
| `audio.cues` | `WHISPER_FLOW_AUDIO_CUES` | bool | `true` |  | Play short start/stop sounds so push-to-talk works eyes-free. |
| `vad.enabled` | `WHISPER_FLOW_VAD_ENABLED` | bool | `true` |  | Two-layer VAD: silence auto-stop plus Silero audio scrubbing before STT. |
| `vad.silence_threshold` | `WHISPER_FLOW_VAD_SILENCE_THRESHOLD` | float | `0.01` |  | RMS energy below this counts as silence. |
| `vad.silence_duration_ms` | `WHISPER_FLOW_VAD_SILENCE_DURATION_MS` | int | `900` |  | Stop after this much continuous silence (VAD and continuous modes). |
| `dictionary.path` | `WHISPER_FLOW_DICTIONARY_PATH` | str | `""` |  | Path to the personal-dictionary TOML; empty uses the default location. |
| `dictionary.enabled` | `WHISPER_FLOW_DICTIONARY_ENABLED` | bool | `true` |  | Apply vocabulary hints and deterministic replacements. |
| `profiles.enabled` | `WHISPER_FLOW_PROFILES_ENABLED` | bool | `true` |  | Apply per-app tone/formatting profiles based on the focused app. |
| `profiles.path` | `WHISPER_FLOW_PROFILES_PATH` | str | `""` |  | Path to the per-app profiles TOML; empty uses the default location. |
| `stt.backend` | `WHISPER_FLOW_STT_BACKEND` | str | `"auto"` | auto, faster_whisper, whispercpp | Speech-to-text engine. 'auto' picks whisper.cpp on macOS, else faster-whisper. |
| `stt.model` | `WHISPER_FLOW_STT_MODEL` | str | `"small.en"` |  | Model name/size to load. |
| `stt.compute_type` | `WHISPER_FLOW_STT_COMPUTE_TYPE` | str | `"int8"` | int8, int8_float16, float16, float32 | faster-whisper compute type. |
| `stt.device` | `WHISPER_FLOW_STT_DEVICE` | str | `"auto"` | auto, cpu, cuda | Compute device for faster-whisper. |
| `stt.unload_after_seconds` | `WHISPER_FLOW_STT_UNLOAD_AFTER_SECONDS` | int | `300` |  | Unload the STT model after this idle period (0 = keep forever). |
| `stt.streaming_preview` | `WHISPER_FLOW_STT_STREAMING_PREVIEW` | bool | `false` |  | Show a live partial transcript (fast model) while you speak. |
| `stt.preview_model` | `WHISPER_FLOW_STT_PREVIEW_MODEL` | str | `"tiny.en"` |  | Fast model used only for the streaming preview. |
| `cleanup.enabled` | `WHISPER_FLOW_CLEANUP_ENABLED` | bool | `true` |  | Run the Ollama LLM cleanup pass on transcripts (core feature). |
| `cleanup.model` | `WHISPER_FLOW_CLEANUP_MODEL` | str | `"gemma3:4b"` |  | Ollama model for cleanup. Models under ~3B may transform meaning. |
| `cleanup.ollama_host` | `WHISPER_FLOW_CLEANUP_OLLAMA_HOST` | str | `"http://localhost:11434"` |  | Base URL of the local Ollama server. |
| `cleanup.min_chars` | `WHISPER_FLOW_CLEANUP_MIN_CHARS` | int | `50` |  | Skip the LLM stage for transcripts shorter than this (latency guard). |
| `cleanup.timeout_seconds` | `WHISPER_FLOW_CLEANUP_TIMEOUT_SECONDS` | float | `8.0` |  | Give up on cleanup after this long and inject the raw transcript. |
| `cleanup.keep_alive` | `WHISPER_FLOW_CLEANUP_KEEP_ALIVE` | str | `"30m"` |  | Ollama keep_alive so the model stays warm between dictations. |
| `cleanup.goal_punctuation` | `WHISPER_FLOW_CLEANUP_GOAL_PUNCTUATION` | bool | `true` |  | Fix punctuation and capitalization. |
| `cleanup.goal_grammar` | `WHISPER_FLOW_CLEANUP_GOAL_GRAMMAR` | bool | `true` |  | Light grammar correction. |
| `cleanup.goal_fillers` | `WHISPER_FLOW_CLEANUP_GOAL_FILLERS` | bool | `true` |  | Remove filler words (um, uh, like). |
| `cleanup.goal_stutters` | `WHISPER_FLOW_CLEANUP_GOAL_STUTTERS` | bool | `true` |  | Collapse stutters and self-corrections. |
| `cleanup.goal_lists` | `WHISPER_FLOW_CLEANUP_GOAL_LISTS` | bool | `true` |  | Format dictated lists. |
| `cleanup.prompt_override` | `WHISPER_FLOW_CLEANUP_PROMPT_OVERRIDE` | str | `""` |  | Custom cleanup system prompt; empty uses the compiled default. |
| `cleanup.instruction_prompt_override` | `WHISPER_FLOW_CLEANUP_INSTRUCTION_PROMPT_OVERRIDE` | str | `""` |  | Custom command-mode (instruction) system prompt; empty uses the default. |
| `cleanup.max_growth_ratio` | `WHISPER_FLOW_CLEANUP_MAX_GROWTH_RATIO` | float | `2.5` |  | Safety net: if cleaned text is longer than this ratio of the raw (a model that answered/expanded instead of cleaning), inject raw instead. |
| `inject.chain` | `WHISPER_FLOW_INJECT_CHAIN` | list[str] | `["clipboard", "keystrokes", "copy_only"]` |  | Ordered injection backends to try, first that works wins. |
| `inject.auto_submit` | `WHISPER_FLOW_INJECT_AUTO_SUBMIT` | bool | `false` |  | Press Enter after injecting (off by default; never surprise the user). |
| `inject.trailing_space` | `WHISPER_FLOW_INJECT_TRAILING_SPACE` | bool | `false` |  | Append a trailing space after injected text. |
| `inject.paste_timeout_seconds` | `WHISPER_FLOW_INJECT_PASTE_TIMEOUT_SECONDS` | float | `2.0` |  | Max time to wait for a clipboard-paste backend to confirm. |
| `history.size` | `WHISPER_FLOW_HISTORY_SIZE` | int | `10` |  | How many recent dictations to keep for re-paste (in memory). |
| `history.persist` | `WHISPER_FLOW_HISTORY_PERSIST` | bool | `false` |  | Persist history to disk (off = audio/text never touch disk). |
| `transparency.enabled` | `WHISPER_FLOW_TRANSPARENCY_ENABLED` | bool | `true` |  | Keep an in-memory log of exactly what was sent to the local LLM. |
| `transparency.size` | `WHISPER_FLOW_TRANSPARENCY_SIZE` | int | `20` |  | How many recent LLM calls to keep (in memory only, never persisted). |
| `ui.enabled` | `WHISPER_FLOW_UI_ENABLED` | bool | `true` |  | Show the tray icon and status overlay. |
| `ui.overlay` | `WHISPER_FLOW_UI_OVERLAY` | bool | `true` |  | Show the live dictation overlay widget (transcript + streaming refinement). |
