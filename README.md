# LinArt Diktat 🎙️

**Local push-to-talk dictation and instant translation for Windows — works in every app, nothing leaves your PC.**

Hold a key, speak, release — the text is typed into whatever field has focus (WhatsApp, Outlook, Word, browser, IDE…).
Select any text and press a key — a translation pops up next to the cursor. Think *Wispr Flow + Google Translate*,
but 100% offline: no account, no cloud, no subscription.

## Features

- **Push-to-talk dictation** – hold `F8`, speak, release. Text is written in the language you spoke.
- **Dictate & translate** – hold `F9`: speak Russian or German, get English (or any language you pick) typed in.
- **Translate anything on screen** – select text, press `F7`: popup with the translation, a language dropdown
  (English, Русский, Deutsch, Polski, Lietuvių, 中文 + 9 more), *Copy* and *Replace selection* buttons.
- **Replace in place** – select your own text, `Shift+F7` → replaced by its translation.
- **Hands-free mode** – `Ctrl+Alt+D` toggles continuous recording.
- **Fast on any GPU** – whisper.cpp and llama.cpp with **Vulkan** (AMD, NVIDIA, Intel); automatic CPU fallback.
  On a Radeon 8060S: ~0.9 s to transcribe 9 s of speech, ~0.5–1 s per translated sentence, ready ~5 s after start.
- **Everything bundled** – one installer, no Python, no LM Studio, nothing downloaded after installation.
- Tray menu in English, German or Russian (follows Windows), start with Windows, custom vocabulary.

## Install

Download the installer from [Releases](https://github.com/Vikinges/linart-diktat/releases) and run it.
No admin rights needed — it installs for the current user into `%LOCALAPPDATA%\Programs\LinArt Diktat`
(~3.5 GB, mostly the two AI models). Windows 10/11 x64, 8 GB RAM minimum, a GPU with Vulkan recommended.

> The installer is not code-signed yet, so Windows SmartScreen may show "Windows protected your PC" →
> *More info* → *Run anyway*.

## Hotkeys

| Key | Action |
|---|---|
| hold `F8` | dictate in the language you speak |
| hold `F9` | dictate + translate (default: English) |
| `F7` | translate selected text (popup) |
| `Shift+F7` | replace selected text with its translation |
| `Ctrl+Alt+D` | hands-free on/off |

On many laptops the F-keys need `Fn` (or switch *Fn lock*). Keys are configurable.

## Configuration

Most settings are in the tray menu. Everything else is in `%APPDATA%\LinArt Diktat\config.json`:

| Key | Meaning |
|---|---|
| `dictate_key`, `dictate_translate_key`, `translate_selection_key`, `replace_selection_key`, `toggle_hotkey` | hotkeys |
| `language` | `auto` or a fixed speech language (`ru`, `de`, `en`, …) |
| `speech_languages` | auto-detect is limited to these (default `["ru","de","en"]`) — fewer wrong-language results |
| `vocabulary` | names/terms Whisper should spell correctly, e.g. `"WAGO, ThingsBoard, Proxmox"` |
| `translate_to` / `translate_to_if_same` | target for `F9` and `Shift+F7` |
| `selection_target` / `selection_target_if_same` | target for the `F7` popup (default Russian; Russian text → English) |
| `translator_url`, `translator_model` | optional: use an OpenAI-compatible server (e.g. LM Studio) instead of the built-in model |

Log file: `%APPDATA%\LinArt Diktat\diktat.log`.

## How it works

```
 hotkey ─► microphone (16 kHz) ─► whisper-server (Whisper large-v3-turbo q8, Vulkan) ─► text
                                                   │ F9
                                                   ▼
                          llama-server (TranslateGemma 4B Q4_K_M, Vulkan) ─► translation ─► pasted into the active app
```

Both engines run as hidden child processes on `127.0.0.1` (random free ports) inside a Windows Job Object,
so they always close together with the app. Nothing listens on the network.

## Build from source

```powershell
git clone https://github.com/Vikinges/linart-diktat.git
cd linart-diktat
powershell -ExecutionPolicy Bypass -File build\download_engines.ps1     # engines + models (~3.4 GB)
python -m venv venv; venv\Scripts\pip install -r requirements.txt
venv\Scripts\python app\linart_diktat.py                                 # run from source
venv\Scripts\python tests\selftest.py some.wav                           # engine smoke test
# installer (needs Inno Setup 6/7):
powershell -ExecutionPolicy Bypass -File build\build.ps1 -Version 2.0.0
```

Version 1.x (PyTorch/ROCm + LM Studio) is in the git history.

## Part of LinArt Local AI

Small, private, offline-first tools that run entirely on your own PC — no cloud, no account, no telemetry:

| Project | What it does |
|---|---|
| [linart-diktat](https://github.com/Vikinges/linart-diktat) | Push-to-talk dictation + instant translation in any app |
| [linart-wissen](https://github.com/Vikinges/linart-wissen) | Ask questions about your own documents (local RAG with citations) |
| [linart-belege](https://github.com/Vikinges/linart-belege) | Receipts & invoices → bookkeeping (German EÜR) with a local vision LLM |
| [linart-3d-studio](https://github.com/Vikinges/linart-3d-studio) | Text/image → 3D model, plus a 3D-print check, on your own GPU |

## Author

**Vladimir Linartas** — founder of [LinArt Labs](https://linart.club), Bavaria, Germany. Self-hosted IoT, embedded systems and local AI.

## License

Apache License 2.0 — see [LICENSE](LICENSE). Bundled engines and models keep their own licenses — see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Gemma is provided under and subject to the
[Gemma Terms of Use](https://ai.google.dev/gemma/terms).
