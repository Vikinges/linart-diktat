"""LinArt Diktat - local push-to-talk dictation + translation for Windows (no cloud).

Hold F8 and speak -> release -> text is typed in the language you spoke.
Hold F9 -> dictate and translate (default: to English). F7 -> translate selected text (popup), Shift+F7 -> replace selection.
Ctrl+Alt+D toggles hands-free dictation (press again to stop).
Speech recognition: Whisper large-v3-turbo on the GPU (PyTorch ROCm/CUDA), CPU fallback via faster-whisper.
Translation and optional cleanup via a local LLM (LM Studio or any OpenAI-compatible server).
Tray icon: grey = ready, red = recording, amber = processing.
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
CFG_FILE = ROOT / "config.json"
LOG = ROOT / "diktat.log"
DEFAULT = {
    "hold_key": "right ctrl",
    "toggle_hotkey": "ctrl+alt+d",
    "language": "auto",            # auto | ru | de | en
    "llm_cleanup": False,
    "llm_url": "http://127.0.0.1:1234/v1",
    "llm_model": "openai/gpt-oss-20b",
    "model_dir": str(ROOT / "models" / "large-v3-turbo"),
    "beep": True,
    "min_seconds": 0.35,
    "vocabulary": "ThingsBoard, Proxmox, Nextcloud, ESP32, LoRa, WAGO",   # names/terms Whisper should spell correctly
}


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def load_cfg() -> dict:
    cfg = dict(DEFAULT)
    try:
        cfg.update(json.loads(CFG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    CFG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg


CFG = load_cfg()

# persistent MIOpen kernel cache: the expensive first-run tuning happens only once
_mi = ROOT / ".miopen"
_mi.mkdir(exist_ok=True)
os.environ.setdefault("MIOPEN_USER_DB_PATH", str(_mi))
os.environ.setdefault("MIOPEN_CUSTOM_CACHE_DIR", str(_mi))

import keyboard            # noqa: E402
import pyperclip           # noqa: E402
import sounddevice as sd   # noqa: E402

SR = 16000
STATE = {"mode": "idle", "frames": [], "toggle": False, "last_text": ""}
LOCK = threading.Lock()
JOBS: "queue.Queue[np.ndarray]" = queue.Queue()
icon = None   # pystray icon, set later


def beep(freq: int, ms: int = 60) -> None:
    if CFG.get("beep"):
        try:
            import winsound
            threading.Thread(target=winsound.Beep, args=(freq, ms), daemon=True).start()
        except Exception:
            pass


def set_mode(m: str) -> None:
    STATE["mode"] = m
    if icon is not None:
        try:
            icon.icon = make_icon(m)
            icon.title = {"idle": "LinArt Diktat – bereit", "rec": "LinArt Diktat – Aufnahme…",
                          "busy": "LinArt Diktat – erkenne…"}.get(m, "LinArt Diktat")
        except Exception:
            pass


# ---------------------------------------------------------------- audio
def _audio_cb(indata, frames, t, status):
    if STATE["mode"] == "rec":
        STATE["frames"].append(indata[:, 0].copy())


stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=_audio_cb, blocksize=1024)
stream.start()


def start_rec() -> None:
    with LOCK:
        if STATE["mode"] == "rec":
            return
        STATE["frames"] = []
        set_mode("rec")
    beep(880)


def stop_rec() -> None:
    with LOCK:
        if STATE["mode"] != "rec":
            return
        audio = np.concatenate(STATE["frames"]) if STATE["frames"] else np.zeros(0, np.float32)
        STATE["frames"] = []
        set_mode("busy")
    beep(620)
    if len(audio) < CFG["min_seconds"] * SR:
        set_mode("idle")
        return
    JOBS.put(audio)


# ---------------------------------------------------------------- recognition
class GpuWhisper:
    """Whisper large-v3-turbo on the Radeon iGPU via PyTorch ROCm (≈4x faster than CPU here)."""

    def __init__(self, model_dir: str):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
        if not torch.cuda.is_available():
            raise RuntimeError("no ROCm GPU")
        self.torch = torch
        self.proc = AutoProcessor.from_pretrained(model_dir)
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(model_dir, torch_dtype=torch.float16).to("cuda").eval()
        self.name = "GPU " + torch.cuda.get_device_name(0)
        tok = self.proc.tokenizer
        self.sot = tok.convert_tokens_to_ids("<|startoftranscript|>")
        self.lang_ids = {k: tok.convert_tokens_to_ids(f"<|{k}|>") for k in ("ru", "de", "en")}
        self._prompt_cache = {}

    def _detect(self, enc_out) -> str:
        # transformers' built-in language detection hangs on ROCm here -> do one decoder step ourselves,
        # restricted to the languages actually spoken (ru/de/en)
        torch = self.torch
        logits = self.model(encoder_outputs=enc_out,
                            decoder_input_ids=torch.tensor([[self.sot]], device="cuda")).logits[0, -1]
        return max(self.lang_ids, key=lambda k: logits[self.lang_ids[k]].item())

    def __call__(self, audio: np.ndarray, lang, vocab: str) -> tuple[str, str]:
        torch = self.torch
        chunks = [audio[i:i + 30 * SR] for i in range(0, len(audio), 30 * SR)] or [audio]
        out, det = [], lang
        if vocab and vocab not in self._prompt_cache:
            self._prompt_cache[vocab] = torch.tensor(self.proc.get_prompt_ids(vocab)).to("cuda")
        for ch in chunks:
            enc = self.proc(ch, sampling_rate=SR, return_tensors="pt", return_attention_mask=True)
            feats = enc.input_features.to("cuda", torch.float16)
            with torch.inference_mode():
                enc_out = self.model.get_encoder()(feats)
                if not det:
                    det = self._detect(enc_out)
                plen = len(self._prompt_cache[vocab]) if vocab else 0
                # Whisper decoder limit is 448 positions incl. prompt + special tokens
                kw = {"max_new_tokens": max(64, 440 - plen - 8), "num_beams": 1, "task": "transcribe",
                      "language": det, "attention_mask": enc.attention_mask.to("cuda")}
                if vocab:
                    kw["prompt_ids"] = self._prompt_cache[vocab]
                # note: generate(encoder_outputs=...) hangs on this ROCm stack -> re-encode (≈0.7 s)
                ids = self.model.generate(feats, **kw)
            txt = self.proc.batch_decode(ids, skip_special_tokens=True)[0].strip()
            if vocab and txt.startswith(vocab.strip()):        # some versions echo the prompt
                txt = txt[len(vocab.strip()):].strip()
            out.append(txt)
        return " ".join(out).strip(), det or "auto"


class CpuWhisper:
    def __init__(self, model_dir: str):
        from faster_whisper import WhisperModel
        self.m = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=16)
        self.name = "CPU (faster-whisper)"

    def __call__(self, audio, lang, vocab):
        segs, info = self.m.transcribe(audio, language=lang, beam_size=1, vad_filter=True,
                                       initial_prompt=vocab or None, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segs).strip(), info.language


log("loading whisper model …")
t0 = time.time()
try:
    MODEL = GpuWhisper(CFG.get("gpu_model_dir") or str(ROOT / "models" / "hf-large-v3-turbo"))
except Exception as e:
    log(f"GPU not available ({e}); using CPU")
    MODEL = CpuWhisper(CFG["model_dir"])
log(f"{MODEL.name} ready in {time.time() - t0:.1f}s")


def _warmup():
    try:
        set_mode("busy")
        t = time.time()
        MODEL(np.random.default_rng(0).normal(0, 0.01, 8 * SR).astype(np.float32), "de", "")
        log(f"warm-up done in {time.time() - t:.1f}s")
    except Exception as e:
        log(f"warm-up failed: {e}")
    finally:
        set_mode("idle")


def transcribe(audio: np.ndarray) -> str:
    lang = None if CFG["language"] == "auto" else CFG["language"]
    # trim leading/trailing silence (simple energy gate) - faster and fewer hallucinations
    env = np.convolve(np.abs(audio), np.ones(800) / 800, mode="same")
    idx = np.nonzero(env > max(0.004, env.max() * 0.05))[0]
    if len(idx):
        audio = audio[max(0, idx[0] - 4000): idx[-1] + 4000]
    text, det = MODEL(audio, lang, CFG.get("vocabulary") or "")
    log(f"[{det}] {len(audio) / SR:.1f}s audio -> {text!r}")
    return text


if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
    import wave
    with wave.open(sys.argv[2]) as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    a = np.interp(np.linspace(0, len(a), int(len(a) * SR / sr)), np.arange(len(a)), a).astype(np.float32)
    import faulthandler
    faulthandler.dump_traceback_later(100, repeat=True)
    _warmup()
    for _ in range(2):
        t = time.time()
        print("SELFTEST:", transcribe(a), f"({time.time() - t:.2f}s)", flush=True)
    os._exit(0)


def cleanup(text: str) -> str:
    body = {"model": CFG["llm_model"], "temperature": 0.1, "max_tokens": 800, "messages": [
        {"role": "system", "content": "Korrigiere diktierten Text minimal: Zeichensetzung, Groß-/Kleinschreibung, "
         "Füllwörter (äh, ähm, ну, э-э) entfernen, offensichtliche Erkennungsfehler. Sprache NICHT ändern, "
         "nichts hinzufügen, nicht umformulieren. Gib nur den korrigierten Text zurück."},
        {"role": "user", "content": text}]}
    req = urllib.request.Request(CFG["llm_url"] + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())["choices"][0]["message"]["content"].strip()
    return out or text


def paste(text: str) -> None:
    if not text:
        return
    try:
        old = pyperclip.paste()
    except Exception:
        old = None
    pyperclip.copy(text + " ")
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    time.sleep(0.25)
    if old is not None:
        try:
            pyperclip.copy(old)
        except Exception:
            pass


import queue  # noqa: E402
# ---------------------------------------------------------------- hotkeys
import tkinter as tk  # noqa: E402
from translate_ui import UIQ, LANGS, Popup, detect_lang, name, selection_target, target_for, translate  # noqa: E402

for k, v in {"dictate_key": "f8", "dictate_translate_key": "f9", "translate_selection_key": "f7",
             "replace_selection_key": "shift+f7", "translate_to": "en", "translate_to_if_german": "ru",
             "llm_model_translate": "qwen/qwen3-vl-30b", "selection_target": "ru", "selection_target_if_same": "en"}.items():
    CFG.setdefault(k, v)
CFG_FILE.write_text(json.dumps(CFG, ensure_ascii=False, indent=1), encoding="utf-8")


def worker() -> None:   # replaces the simple worker: jobs are (audio, translate?)
    while True:
        audio, do_tr = JOBS.get()
        do_tr = do_tr or bool(CFG.get("always_translate"))
        try:
            t = time.time()
            text = transcribe(audio)
            if text and do_tr:
                src = detect_lang(text)
                tgt = target_for(src, CFG)
                text = translate(text, tgt, CFG)
                log(f"translated {src}->{tgt}: {text!r}")
            elif text and CFG.get("llm_cleanup"):
                try:
                    text = cleanup(text)
                except Exception as e:
                    log(f"LLM cleanup skipped: {e}")
            STATE["last_text"] = text
            paste(text)
            log(f"done in {time.time() - t:.1f}s")
        except Exception as e:
            log(f"ERROR: {type(e).__name__}: {e}")
            beep(300, 200)
        finally:
            set_mode("idle")


threading.Thread(target=worker, daemon=True).start()
STATE["translate_next"] = False


def stop_rec_mode() -> None:
    with LOCK:
        if STATE["mode"] != "rec":
            return
        audio = np.concatenate(STATE["frames"]) if STATE["frames"] else np.zeros(0, np.float32)
        STATE["frames"] = []
        set_mode("busy")
    beep(620)
    if len(audio) < CFG["min_seconds"] * SR:
        set_mode("idle")
        return
    JOBS.put((audio, STATE.get("translate_next", False)))


stop_rec = stop_rec_mode   # older code paths use stop_rec


def _hold(key: str, translate_mode: bool):
    def down(e):
        if not STATE["toggle"] and STATE["mode"] == "idle":
            STATE["translate_next"] = translate_mode
            log(f"key down: {key} (translate={translate_mode})")
            start_rec()

    def up(e):
        if not STATE["toggle"]:
            stop_rec_mode()
    try:
        keyboard.on_press_key(key, down, suppress=True)
        keyboard.on_release_key(key, up, suppress=True)
        log(f"hold key: {key} (translate={translate_mode})")
    except Exception as e:
        log(f"cannot bind {key!r}: {e}")


def on_toggle():
    if STATE["toggle"]:
        STATE["toggle"] = False
        stop_rec_mode()
    elif STATE["mode"] == "idle":
        STATE["toggle"] = True
        STATE["translate_next"] = False
        start_rec()


_hold(CFG["dictate_key"], False)
_hold(CFG["dictate_translate_key"], True)
if CFG.get("hold_key"):
    _hold(CFG["hold_key"], False)          # legacy key (right ctrl), harmless if not present
keyboard.add_hotkey(CFG["toggle_hotkey"], on_toggle)


# ---------------------------------------------------------------- selection translation
def _grab_selection() -> str:
    try:
        old = pyperclip.paste()
    except Exception:
        old = ""
    pyperclip.copy("")
    for k in ("shift", "alt", "ctrl"):
        try:
            keyboard.release(k)
        except Exception:
            pass
    time.sleep(0.05)
    keyboard.send("ctrl+c")
    sel = ""
    for _ in range(20):
        time.sleep(0.04)
        sel = pyperclip.paste()
        if sel:
            break
    try:
        pyperclip.copy(old)
    except Exception:
        pass
    return sel.strip()


def _cursor_pos():
    import ctypes

    class P(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    p = P()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def run_popup_translation(sel: str, tgt: str, x: int, y: int) -> None:
    src = detect_lang(sel)
    UIQ.put(("show", x, y, f"{name(src)} → {name(tgt)} · перевожу…", sel[:400], True, sel, tgt))
    set_mode("busy")
    try:
        t = time.time()
        out = translate(sel, tgt, CFG)
        log(f"selection {src}->{tgt} {len(sel)} chars in {time.time() - t:.1f}s")
        UIQ.put(("show", x, y, f"{name(src)} → {name(tgt)} · {time.time() - t:.1f} c · Esc", out, False, sel, tgt))
    except Exception as e:
        log(f"translate ERROR: {e}")
        UIQ.put(("show", x, y, "Ошибка перевода", f"{e}\n\nLM Studio запущен? Модель загружена?", False, sel, tgt))
    finally:
        set_mode("idle")


def translate_selection(replace: bool) -> None:
    sel = _grab_selection()
    if not sel:
        beep(300, 120)
        return
    src = detect_lang(sel)
    if not replace:
        x, y = _cursor_pos()
        run_popup_translation(sel, selection_target(src, CFG), x, y)
        return
    tgt = target_for(src, CFG)
    set_mode("busy")
    try:
        out = translate(sel, tgt, CFG)
        log(f"replace {src}->{tgt} {len(sel)} chars")
        paste(out.rstrip() if out else sel)
    except Exception as e:
        log(f"translate ERROR: {e}")
        beep(300, 200)
    finally:
        set_mode("idle")


keyboard.add_hotkey(CFG["translate_selection_key"], lambda: threading.Thread(target=translate_selection, args=(False,), daemon=True).start())
keyboard.add_hotkey(CFG["replace_selection_key"], lambda: threading.Thread(target=translate_selection, args=(True,), daemon=True).start())

# ---------------------------------------------------------------- tray (detached) + Tk main loop
from PIL import Image, ImageDraw  # noqa: E402
import pystray  # noqa: E402


def make_icon(mode: str) -> Image.Image:
    col = {"idle": (140, 150, 160), "rec": (226, 67, 67), "busy": (240, 162, 74)}.get(mode, (140, 150, 160))
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((22, 6, 42, 38), radius=10, fill=col)
    d.arc((14, 18, 50, 46), 0, 180, fill=col, width=4)
    d.line((32, 46, 32, 56), fill=col, width=4)
    d.line((22, 57, 42, 57), fill=col, width=4)
    return im


def _set(key, val):
    def f(icon_, item):
        CFG[key] = val
        CFG_FILE.write_text(json.dumps(CFG, ensure_ascii=False, indent=1), encoding="utf-8")
    return f


def _toggle(key):
    def f(icon_, item):
        CFG[key] = not CFG.get(key)
        CFG_FILE.write_text(json.dumps(CFG, ensure_ascii=False, indent=1), encoding="utf-8")
    return f


def _quit(icon_, item):
    icon_.stop()
    os._exit(0)


K = lambda s: s.upper()
menu = pystray.Menu(
    pystray.MenuItem(f"Диктовка: держать {K(CFG['dictate_key'])}  ·  с переводом: держать {K(CFG['dictate_translate_key'])}", None, enabled=False),
    pystray.MenuItem(f"Перевод выделенного: {K(CFG['translate_selection_key'])}  ·  заменить: {K(CFG['replace_selection_key'])}", None, enabled=False),
    pystray.MenuItem("Всегда переводить диктовку (любая клавиша)", _toggle("always_translate"), checked=lambda it: CFG.get("always_translate")),
    pystray.MenuItem("Язык речи", pystray.Menu(*[
        pystray.MenuItem(lbl, _set("language", code), checked=lambda it, c=code: CFG["language"] == c, radio=True)
        for lbl, code in (("Автоматически", "auto"), ("Русский", "ru"), ("Deutsch", "de"), ("English", "en"))])),
    pystray.MenuItem("Диктовку переводить на", pystray.Menu(*[
        pystray.MenuItem(n, _set("translate_to", c), checked=lambda it, c=c: CFG["translate_to"] == c, radio=True)
        for c, n, _ in LANGS[:6]])),
    pystray.MenuItem(f"{K(CFG['translate_selection_key'])} (чужой текст) переводить на", pystray.Menu(*[
        pystray.MenuItem(n, _set("selection_target", c), checked=lambda it, c=c: CFG["selection_target"] == c, radio=True)
        for c, n, _ in LANGS[:6]])),
    pystray.MenuItem("Если речь уже на этом языке — переводить на", pystray.Menu(*[
        pystray.MenuItem(n, _set("translate_to_if_german", c), checked=lambda it, c=c: CFG["translate_to_if_german"] == c, radio=True)
        for c, n, _ in LANGS[:6]])),
    pystray.MenuItem("Сглаживать диктовку локальной LLM", _toggle("llm_cleanup"), checked=lambda it: CFG.get("llm_cleanup")),
    pystray.MenuItem("Звуковые сигналы", _toggle("beep"), checked=lambda it: CFG.get("beep")),
    pystray.MenuItem("Вставить последний текст ещё раз", lambda i, it: paste(STATE["last_text"])),
    pystray.MenuItem("Журнал", lambda i, it: os.startfile(str(LOG))),
    pystray.MenuItem("Выход", _quit),
)
icon = pystray.Icon("linart_diktat", make_icon("idle"), "LinArt Diktat", menu)
icon.run_detached()
threading.Thread(target=_warmup, daemon=True).start()
log(f"ready: {CFG['dictate_key']} / {CFG['dictate_translate_key']} / {CFG['translate_selection_key']} · {MODEL.name}")

root = tk.Tk()
root.withdraw()
popup = Popup(root, on_replace=lambda t: threading.Thread(target=lambda: (time.sleep(0.15), paste(t)), daemon=True).start(),
              on_retranslate=lambda s_, t_, x_, y_: threading.Thread(target=run_popup_translation, args=(s_, t_, x_, y_), daemon=True).start())


def _pump():
    try:
        while True:
            msg = UIQ.get_nowait()
            if msg[0] == "show":
                popup.show(*msg[1:])
    except queue.Empty:
        pass
    root.after(60, _pump)


root.after(60, _pump)
root.mainloop()
