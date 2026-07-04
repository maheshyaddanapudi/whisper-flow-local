# Configuration reference

_Generated from the config schema — do not edit by hand._

| Key | Type | Default | Choices | Description |
| --- | --- | --- | --- | --- |
| `general.language` | str | `"auto"` |  | Spoken language hint for STT ('auto' to detect). |
| `general.max_recording_seconds` | int | `300` |  | Hard safety cap on a single recording. |
| `hotkey.primary` | str | `"ctrl+shift+space"` |  | Global hotkey for dictation (tap = toggle, hold = push-to-talk). |
| `hotkey.mode` | str | `"hybrid"` | hybrid, toggle, push_to_talk, continuous | Recording mode for the primary hotkey. |
| `hotkey.hold_threshold_ms` | int | `500` |  | Hold longer than this to act as push-to-talk; shorter is a toggle tap. |
| `hotkey.min_duration_ms` | int | `150` |  | Recordings shorter than this are discarded as accidental taps. |
| `hotkey.release_grace_ms` | int | `500` |  | Grace period after PTT key release before stopping capture. |
| `hotkey.backend` | str | `"auto"` | auto, pynput, evdev, quartz, none | Hotkey listener backend. |
| `audio.sample_rate` | int | `16000` | 8000, 16000, 22050, 44100, 48000 | Capture sample rate in Hz (Whisper-native is 16000). |
| `audio.device` | str | `""` |  | Input device name substring; empty uses the system default. |
| `audio.chunk_ms` | int | `500` |  | Audio capture chunk size in milliseconds. |
| `audio.cues` | bool | `true` |  | Play short start/stop sounds so push-to-talk works eyes-free. |
| `stt.backend` | str | `"auto"` | auto, faster_whisper, whispercpp | Speech-to-text engine. 'auto' picks whisper.cpp on macOS, else faster-whisper. |
| `stt.model` | str | `"small.en"` |  | Model name/size to load. |
| `stt.compute_type` | str | `"int8"` | int8, int8_float16, float16, float32 | faster-whisper compute type. |
| `stt.device` | str | `"auto"` | auto, cpu, cuda | Compute device for faster-whisper. |
| `stt.unload_after_seconds` | int | `300` |  | Unload the STT model after this idle period (0 = keep forever). |
| `cleanup.enabled` | bool | `true` |  | Run the Ollama LLM cleanup pass on transcripts (core feature). |
| `cleanup.model` | str | `"gemma3:4b"` |  | Ollama model for cleanup. Models under ~3B may transform meaning. |
| `cleanup.ollama_host` | str | `"http://localhost:11434"` |  | Base URL of the local Ollama server. |
| `cleanup.min_chars` | int | `50` |  | Skip the LLM stage for transcripts shorter than this (latency guard). |
| `cleanup.timeout_seconds` | float | `8.0` |  | Give up on cleanup after this long and inject the raw transcript. |
| `cleanup.keep_alive` | str | `"30m"` |  | Ollama keep_alive so the model stays warm between dictations. |
| `cleanup.goal_punctuation` | bool | `true` |  | Fix punctuation and capitalization. |
| `cleanup.goal_grammar` | bool | `true` |  | Light grammar correction. |
| `cleanup.goal_fillers` | bool | `true` |  | Remove filler words (um, uh, like). |
| `cleanup.goal_stutters` | bool | `true` |  | Collapse stutters and self-corrections. |
| `cleanup.goal_lists` | bool | `true` |  | Format dictated lists. |
| `cleanup.prompt_override` | str | `""` |  | Custom cleanup system prompt; empty uses the compiled default. |
| `inject.chain` | list[str] | `["clipboard", "keystrokes", "copy_only"]` |  | Ordered injection backends to try, first that works wins. |
| `inject.auto_submit` | bool | `false` |  | Press Enter after injecting (off by default; never surprise the user). |
| `inject.trailing_space` | bool | `false` |  | Append a trailing space after injected text. |
| `inject.paste_timeout_seconds` | float | `2.0` |  | Max time to wait for a clipboard-paste backend to confirm. |
| `history.size` | int | `10` |  | How many recent dictations to keep for re-paste (in memory). |
| `history.persist` | bool | `false` |  | Persist history to disk (off = audio/text never touch disk). |
| `ui.enabled` | bool | `true` |  | Show the tray icon and status overlay. |
