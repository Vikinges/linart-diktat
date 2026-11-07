# LinArt Diktat 🎙️

**Local push-to-talk dictation and instant translation for Windows — works in every app, nothing leaves your PC.**

Hold a key, speak, release — the text is typed into whatever field has focus (WhatsApp, Outlook, Word, browser, IDE…).
Select any text and press a key — a translation pops up next to the cursor. Think *Wispr Flow + Google Translate*, but 100% offline.

## Features

- **Push-to-talk dictation** – hold `F8`, speak, release. Text is written in the language you spoke (Russian, German, English auto-detected).
- **Dictate & translate** – hold `F9`: speak Russian or German, get English (or any language you pick) typed in.
- **Translate anything on screen** – select text, press `F7`: popup with the translation, a language dropdown
  (English, Русский, Deutsch, Polski, Lietuvių, 中文 + more), *Copy* and *Replace selection* buttons.
- **Replace in place** – select your own text, `Shift+F7` → replaced by its translation.
- **Hands-free mode** – `Ctrl+Alt+D` toggles continuous recording.
- **GPU accelerated** – Whisper large-v3-turbo on AMD (ROCm) or NVIDIA (CUDA); ~2.5 s for 9 s of speech on a Radeon 8060S iGPU.
  Automatic CPU fallback via faster-whisper.
- **Custom vocabulary** – teach it your product names and jargon so they are spelled right.
- **Tray icon** – grey = ready, red = recording, amber = processing; all settings in the tray menu.

Translation (≈0.5–0.8 s per sentence) and optional text clean-up use a **local LLM** via any OpenAI-compatible
server, e.g. [LM Studio](https://lmstudio.ai) (tested with `qwen/qwen3-vl-30b`).

## Install (Windows 10/11, Python 3.12)

```powershell
git clone https://github.com/Vikinges/linart-diktat.git
cd linart-diktat
python -m venv venv
venv\Scripts\activate
```

### PyTorch for your GPU

Install PyTorch **before** the requirements, matching your hardware:

```powershell
# AMD Ryzen AI MAX / Radeon 8060S (gfx1151) - ROCm nightly for Windows
pip install --pre torch --index-url https://rocm.nightlies.amd.com/v2/gfx1151/
# NVIDIA
pip install torch --index-url https://download.pytorch.org/whl/cu128
# CPU only
pip install torch
```

```powershell
pip install -r requirements.txt
python download_models.py          # ~3 GB: Whisper large-v3-turbo (GPU + CPU variants)
copy config.example.json config.json
start_diktat.bat
```

For translation, start LM Studio, load a model and enable the local server (`http://127.0.0.1:1234`).
To start with Windows, put a shortcut to `start_diktat.bat` into `shell:startup`.

## Hotkeys

| Key | Action |
|---|---|
| hold `F8` | dictate in the language you speak |
| hold `F9` | dictate + translate (default: English) |
| `F7` | translate selected text (popup) |
| `Shift+F7` | replace selected text with its translation |
| `Ctrl+Alt+D` | hands-free on/off |

On many laptops the F-keys need `Fn`. All keys are configurable in `config.json`
(`dictate_key`, `dictate_translate_key`, `translate_selection_key`, `replace_selection_key`, `toggle_hotkey`).

## Configuration (`config.json`)

| Key | Meaning |
|---|---|
| `language` | `auto`, `ru`, `de`, `en` |
| `vocabulary` | comma-separated terms Whisper should spell correctly |
| `translate_to` / `translate_to_if_german` | target language for `F9` dictation & `Shift+F7` |
| `selection_target` / `selection_target_if_same` | target for the `F7` popup (default: Russian, Russian text → English) |
| `always_translate` | translate every dictation, whatever key is used |
| `llm_url`, `llm_model_translate`, `llm_model` | local LLM endpoint and models |
| `llm_cleanup` | let the LLM fix punctuation and filler words |

## Notes for AMD Strix Halo (gfx1151) on Windows

- First GPU run tunes MIOpen kernels (≈30 s); the cache is kept in `.miopen/`, later starts are fast.
- Whisper language auto-detect in transformers is replaced by a fast ru/de/en scorer; the decoder budget
  respects Whisper's 448-token limit including the vocabulary prompt.

## Part of LinArt Local AI

Small, private, offline-first tools that run entirely on your own PC — no cloud, no account, no telemetry:

| Project | What it does |
|---|---|
| [linart-diktat](https://github.com/Vikinges/linart-diktat) | Push-to-talk dictation + instant translation in any app |
| [linart-wissen](https://github.com/Vikinges/linart-wissen) | Ask questions about your own documents (local RAG with citations) |
| [linart-belege](https://github.com/Vikinges/linart-belege) | Receipts & invoices → bookkeeping (German EÜR) with a local vision LLM |
| [linart-3d-studio](https://github.com/Vikinges/linart-3d-studio) | Text/image → 3D model, plus a 3D-print check, on your own GPU |

Built and tested on an HP ZBook Ultra G1a (AMD Ryzen AI MAX+ PRO 395, Radeon 8060S, 128 GB unified memory) under Windows 11 with PyTorch ROCm, and designed to also run on NVIDIA (CUDA) or CPU.

## Author

**Vladimir Linartas** — founder of [LinArt Labs](https://linart.club), Bavaria, Germany. Self-hosted IoT, embedded systems and local AI.

## License

Apache License 2.0 — see [LICENSE](LICENSE). Third-party models are downloaded separately and keep their own licenses.
