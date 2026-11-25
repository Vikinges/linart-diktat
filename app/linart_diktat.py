"""LinArt Diktat - local push-to-talk dictation and translation for Windows. Nothing leaves your PC.

  hold F8        dictate in the language you speak
  hold F9        dictate + translate (default: English)
  F7             translate the selected text (popup with language list)
  Shift+F7       replace the selected text with its translation
  Ctrl+Alt+D     hands-free dictation on/off

Speech: whisper.cpp (Whisper large-v3-turbo), translation: llama.cpp + TranslateGemma 4B,
both on the GPU via Vulkan (AMD / NVIDIA / Intel) with automatic CPU fallback.
"""
from __future__ import annotations

import ctypes
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import winreg
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui import LANGS, T, UIQ, Indicator, Popup, detect_lang, name  # noqa: E402
import engines  # noqa: E402

APP = "LinArt Diktat"
VERSION = "2.0.3"
DATA = Path(os.environ.get("APPDATA", Path.home())) / APP
DATA.mkdir(parents=True, exist_ok=True)
CFG_FILE = DATA / "config.json"
LOG = DATA / "diktat.log"

DEFAULT = {
    "dictate_key": "f8",
    "dictate_translate_key": "f9",
    "translate_selection_key": "f7",
    "replace_selection_key": "shift+f7",
    "toggle_hotkey": "ctrl+alt+d",
    "language": "auto",                       # auto | ru | de | en | ...
    "speech_languages": ["ru", "de", "en"],   # auto-detect is limited to these
    "translate_to": "en",                     # F9 / Shift+F7 target
    "translate_to_if_same": "ru",             # ... if the text is already in translate_to
    "selection_target": "ru",                 # F7 popup target
    "selection_target_if_same": "en",
    "always_translate": False,
    "vocabulary": "",                         # names/terms Whisper should spell correctly
    "beep": True,
    "show_indicator": True,
    "min_seconds": 0.35,
    "translator_url": "",                     # optional: OpenAI-compatible server instead of built-in model
    "translator_model": "",
}


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_cfg() -> dict:
    c = dict(DEFAULT)
    try:
        c.update(json.loads(CFG_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return c


def save_cfg() -> None:
    try:
        CFG_FILE.write_text(json.dumps(CFG, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        log(f"config save failed: {e}")


CFG = load_cfg()
save_cfg()

# ---------------------------------------------------------------- single instance
_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\LinArtDiktatSingleInstance")
if ctypes.windll.kernel32.GetLastError() == 183:
    ctypes.windll.user32.MessageBoxW(None, T["running"], APP, 0x40)
    sys.exit(0)

import keyboard            # noqa: E402
import pyperclip           # noqa: E402
import pystray             # noqa: E402
import sounddevice as sd   # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

SR = 16000
STATE = {"mode": "loading", "frames": [], "toggle": False, "last_text": "", "translate_next": False}
LOCK = threading.Lock()
JOBS: "queue.Queue" = queue.Queue()
icon = None

WHISPER = engines.Whisper(DATA, engines.cpu_threads())
TRANSLATOR = engines.Translator(DATA, lambda: CFG)


_TONES: dict = {}


def _tone(freq: int, ms: int) -> bytes:
    """Short soft sine tone as an in-memory WAV (played through the normal speakers/headset)."""
    if (freq, ms) not in _TONES:
        sr = 22050
        t = np.arange(int(sr * ms / 1000)) / sr
        env = np.minimum(1.0, np.minimum(t, t[-1] - t) * 150)          # ~7 ms fade in/out, no clicks
        _TONES[(freq, ms)] = engines._wav_bytes((0.3 * np.sin(2 * np.pi * freq * t) * env).astype(np.float32), sr)
    return _TONES[(freq, ms)]


def beep(freq: int, ms: int = 90) -> None:
    if CFG.get("beep"):
        try:
            import winsound
            data = _tone(freq, ms)
            threading.Thread(target=winsound.PlaySound, args=(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT),
                             daemon=True).start()
        except Exception:
            pass


def indicate(mode: str) -> None:
    if not CFG.get("show_indicator", True):
        mode = "idle"
    text = {"rec": T["ind_rec_tr"] if STATE.get("translate_next") else T["ind_rec"],
            "busy": T["ind_busy"], "tr": T["ind_tr"]}.get(mode, "")
    UIQ.put(("ind", mode if mode in ("rec", "busy", "tr") else "idle", text))


def make_icon(mode: str) -> Image.Image:
    col = {"idle": (140, 150, 160), "rec": (226, 67, 67), "busy": (240, 162, 74),
           "loading": (90, 130, 200)}.get(mode, (140, 150, 160))
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((22, 6, 42, 38), radius=10, fill=col)
    d.arc((14, 18, 50, 46), 0, 180, fill=col, width=4)
    d.line((32, 46, 32, 56), fill=col, width=4)
    d.line((22, 57, 42, 57), fill=col, width=4)
    return im


def set_mode(m: str) -> None:
    STATE["mode"] = m
    indicate(m)
    if icon is not None:
        try:
            icon.icon = make_icon(m)
            icon.title = {"idle": T["ready"], "rec": T["rec"], "busy": T["busy"], "loading": T["loading"]}.get(m, APP)
        except Exception:
            pass


# ---------------------------------------------------------------- audio
def _audio_cb(indata, frames, t, status):
    STATE["last_audio"] = time.time()
    if STATE["mode"] == "rec":
        STATE["frames"].append(indata[:, 0].copy())


stream = None
STREAM_LOCK = threading.Lock()
STATE["last_audio"] = 0.0


def open_stream(reason: str = "") -> bool:
    """(Re)open the microphone. After sleep or a headset change PortAudio has to re-enumerate devices,
    otherwise the old stream silently stops delivering audio."""
    global stream
    with STREAM_LOCK:
        if stream is not None:
            try:
                stream.abort()
                stream.close()
            except Exception:
                pass
            stream = None
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass
        try:
            stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=_audio_cb, blocksize=1024)
            stream.start()
            STATE["last_audio"] = time.time()
            if reason:
                log(f"watchdog: microphone reopened ({reason})")
            return True
        except Exception as e:
            log(f"microphone error ({reason or 'open'}): {e}")
            return False


def audio_alive(max_age: float = 1.5) -> bool:
    return stream is not None and stream.active and time.time() - STATE.get("last_audio", 0) < max_age


def start_rec() -> None:
    if not audio_alive():
        open_stream("no audio at key press")
    with LOCK:
        if STATE["mode"] not in ("idle",):
            return
        STATE["rec_started"] = time.time()
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
        held = time.time() - STATE.get("rec_started", time.time())
        if held >= CFG["min_seconds"]:
            log(f"watchdog: key held {held:.1f}s but got {len(audio) / SR:.2f}s audio -> reopening microphone")
            beep(300, 200)
            threading.Thread(target=open_stream, args=("recording was empty",), daemon=True).start()
        set_mode("idle")
        return
    JOBS.put((audio, STATE.get("translate_next", False)))


def trim(audio: np.ndarray) -> np.ndarray:
    env = np.convolve(np.abs(audio), np.ones(800) / 800, mode="same")
    idx = np.nonzero(env > max(0.004, env.max() * 0.05))[0]
    return audio[max(0, idx[0] - 4000): idx[-1] + 4000] if len(idx) else audio


def target_for(src: str) -> str:
    t = CFG["translate_to"]
    return CFG["translate_to_if_same"] if src == t else t


def selection_target(src: str) -> str:
    t = CFG["selection_target"]
    return CFG["selection_target_if_same"] if src == t else t


# ---------------------------------------------------------------- output
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


def worker() -> None:
    while True:
        audio, do_tr = JOBS.get()
        do_tr = do_tr or bool(CFG.get("always_translate"))
        try:
            t = time.time()
            audio = trim(audio)
            lang = None if CFG["language"] == "auto" else CFG["language"]
            # punctuation style prompt in the language the user spoke last time (+ custom vocabulary)
            plang = lang or STATE.get("last_lang") or (CFG.get("speech_languages") or ["en"])[0]
            prompt = (engines.STYLE_PROMPT.get(plang, "") + " " + CFG.get("vocabulary", "")).strip()
            text, det = WHISPER.transcribe(audio, SR, lang, CFG.get("speech_languages") or [], prompt)
            if det:
                STATE["last_lang"] = det
            log(f"[{det}] {len(audio) / SR:.1f}s -> {text!r} ({time.time() - t:.1f}s)")
            if text and do_tr:
                src = det or detect_lang(text)
                tgt = target_for(src)
                indicate("tr")
                text = TRANSLATOR.translate(text, src, tgt)
                log(f"translated {src}->{tgt}: {text!r}")
            STATE["last_text"] = text
            paste(text)
            log(f"done in {time.time() - t:.1f}s")
        except Exception as e:
            log(f"ERROR: {type(e).__name__}: {e}")
            beep(300, 200)
        finally:
            set_mode("idle")


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
    class P(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    p = P()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def run_popup_translation(sel: str, tgt: str, x: int, y: int) -> None:
    src = detect_lang(sel)
    UIQ.put(("show", x, y, f"{name(src)} â†’ {name(tgt)} Â· {T['translating']}", sel[:400], True, sel, tgt))
    try:
        t = time.time()
        out = TRANSLATOR.translate(sel, src, tgt)
        log(f"selection {src}->{tgt} {len(sel)} chars in {time.time() - t:.1f}s")
        UIQ.put(("show", x, y, f"{name(src)} â†’ {name(tgt)} Â· {time.time() - t:.1f} s Â· Esc", out, False, sel, tgt))
    except Exception as e:
        log(f"translate ERROR: {e}")
        UIQ.put(("show", x, y, T["error"], str(e), False, sel, tgt))


def translate_selection(replace: bool) -> None:
    if STATE["mode"] == "loading":
        beep(300, 120)
        return
    sel = _grab_selection()
    if not sel:
        beep(300, 120)
        return
    src = detect_lang(sel)
    if not replace:
        x, y = _cursor_pos()
        run_popup_translation(sel, selection_target(src), x, y)
        return
    tgt = target_for(src)
    try:
        paste(TRANSLATOR.translate(sel, src, tgt).rstrip() or sel)
    except Exception as e:
        log(f"translate ERROR: {e}")
        beep(300, 200)


# ---------------------------------------------------------------- hotkeys
def _hold(key: str, translate_mode: bool):
    def down(e):
        if not STATE["toggle"] and STATE["mode"] == "idle":
            STATE["translate_next"] = translate_mode
            start_rec()

    def up(e):
        if not STATE["toggle"]:
            stop_rec()
    try:
        keyboard.on_press_key(key, down, suppress=True)
        keyboard.on_release_key(key, up, suppress=True)
        log(f"hold key: {key} (translate={translate_mode})")
    except Exception as e:
        log(f"cannot bind {key!r}: {e}")


def on_toggle():
    if STATE["toggle"]:
        STATE["toggle"] = False
        stop_rec()
    elif STATE["mode"] == "idle":
        STATE["toggle"] = True
        STATE["translate_next"] = False
        start_rec()


def bind_hotkeys():
    _hold(CFG["dictate_key"], False)
    _hold(CFG["dictate_translate_key"], True)
    for key, fn in ((CFG["toggle_hotkey"], on_toggle),
                    (CFG["translate_selection_key"], lambda: threading.Thread(target=translate_selection, args=(False,), daemon=True).start()),
                    (CFG["replace_selection_key"], lambda: threading.Thread(target=translate_selection, args=(True,), daemon=True).start())):
        try:
            keyboard.add_hotkey(key, fn)
        except Exception as e:
            log(f"cannot bind {key!r}: {e}")


# ---------------------------------------------------------------- watchdog
PROBE_SCAN = 0x76          # F24: not on real keyboards; suppressed, never reaches other apps
STATE["ui_alive"] = time.time()


def _kb_probe() -> bool:
    """Inject F24 and check that our low-level keyboard hook still sees it.
    Windows silently removes hooks that respond too slowly (e.g. after sleep or heavy load).
    keyboard.send() cannot type F24 on some layouts (DE), so use keybd_event directly."""
    ev = threading.Event()
    h = keyboard.hook_key("f24", lambda e: ev.set(), suppress=True)
    try:
        ctypes.windll.user32.keybd_event(0x87, PROBE_SCAN, 0, 0)
        ctypes.windll.user32.keybd_event(0x87, PROBE_SCAN, 2, 0)
        return ev.wait(1.5)
    finally:
        try:
            keyboard.unhook(h)
        except Exception:
            pass


def restart_self(reason: str) -> None:
    """Start a fresh copy after a short delay (the single-instance mutex must be released first), then exit."""
    import subprocess
    log(f"watchdog: {reason} -> restarting")
    if getattr(sys, "frozen", False):
        cmd = f'start "" "{sys.executable}"'
    else:
        cmd = f'start "" "{sys.executable}" "{Path(__file__).resolve()}"'
    try:
        subprocess.Popen(f"cmd /c timeout /t 3 /nobreak >nul & {cmd}", shell=True, creationflags=0x08000000)
    except Exception as e:
        log(f"watchdog: cannot schedule restart: {e}")
        return
    for srv in (WHISPER.srv, TRANSLATOR.srv):
        try:
            srv.stop()
        except Exception:
            pass
    os._exit(3)


def watchdog() -> None:
    """Every 10 s: microphone delivers audio, keyboard hook sees keys (probe every 60 s), UI loop is alive."""
    while STATE["mode"] == "loading":
        time.sleep(2)
    time.sleep(3)
    probe_ok = _kb_probe()
    log(f"watchdog: started (keyboard probe {'ok' if probe_ok else 'not supported - disabled'})")
    kb_fail, last_probe = 0, time.time()
    while True:
        time.sleep(10)
        idle = STATE["mode"] == "idle" and not STATE["toggle"]
        if time.time() - STATE["ui_alive"] > 90:
            restart_self(f"UI loop hung for {time.time() - STATE['ui_alive']:.0f}s")
        if idle and not audio_alive(5.0):
            open_stream("stream stopped delivering audio")
        if probe_ok and idle and time.time() - last_probe > 60:
            last_probe = time.time()
            if _kb_probe():
                kb_fail = 0
            else:
                kb_fail += 1
                log(f"watchdog: keyboard hook did not see the probe key ({kb_fail}x)")
                if kb_fail >= 2:
                    restart_self("keyboard hook lost")


# ---------------------------------------------------------------- autostart (HKCU Run key)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
            return True
    except OSError:
        return False


def toggle_autostart(icon_=None, item=None):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if autostart_enabled():
            winreg.DeleteValue(k, APP)
        else:
            exe = sys.executable if getattr(sys, "frozen", False) else f'"{sys.executable}" "{Path(__file__).resolve()}"'
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, f'"{exe}"' if getattr(sys, "frozen", False) else exe)


# ---------------------------------------------------------------- tray
def _set(key, val):
    def f(icon_, item):
        CFG[key] = val
        save_cfg()
    return f


def _toggle(key):
    def f(icon_, item):
        CFG[key] = not CFG.get(key)
        save_cfg()
    return f


def _quit(icon_, item):
    icon_.stop()
    WHISPER.srv.stop()
    TRANSLATOR.srv.stop()
    os._exit(0)


def lang_menu(key):
    return pystray.Menu(*[pystray.MenuItem(n, _set(key, c), checked=lambda it, c=c: CFG[key] == c, radio=True)
                          for c, n, _ in LANGS[:6]])


K = lambda s: s.upper()   # noqa: E731
menu = pystray.Menu(
    pystray.MenuItem(T["hk1"].format(a=K(CFG["dictate_key"]), b=K(CFG["dictate_translate_key"])), None, enabled=False),
    pystray.MenuItem(T["hk2"].format(a=K(CFG["translate_selection_key"]), b=K(CFG["replace_selection_key"])), None, enabled=False),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem(T["dict_to"], lang_menu("translate_to")),
    pystray.MenuItem(T["sel_to"].format(k=K(CFG["translate_selection_key"])), lang_menu("selection_target")),
    pystray.MenuItem(T["same_to"], lang_menu("translate_to_if_same")),
    pystray.MenuItem(T["speech"], pystray.Menu(
        pystray.MenuItem(T["auto"], _set("language", "auto"), checked=lambda it: CFG["language"] == "auto", radio=True),
        *[pystray.MenuItem(n, _set("language", c), checked=lambda it, c=c: CFG["language"] == c, radio=True)
          for c, n, _ in LANGS[:6]])),
    pystray.MenuItem(T["always"], _toggle("always_translate"), checked=lambda it: CFG.get("always_translate")),
    pystray.Menu.SEPARATOR,
    pystray.MenuItem(T["indicator"], _toggle("show_indicator"), checked=lambda it: CFG.get("show_indicator", True)),
    pystray.MenuItem(T["beep"], _toggle("beep"), checked=lambda it: CFG.get("beep")),
    pystray.MenuItem(T["autostart"], toggle_autostart, checked=lambda it: autostart_enabled()),
    pystray.MenuItem(T["again"], lambda i, it: paste(STATE["last_text"])),
    pystray.MenuItem(T["log"], lambda i, it: os.startfile(str(LOG))),
    pystray.MenuItem(f"{T['quit']}  (v{VERSION})", _quit),
)


def boot():
    t = time.time()
    open_stream()
    ok_w = WHISPER.srv.start()
    log(f"whisper {'GPU' if WHISPER.srv.gpu else 'CPU'} ready={ok_w} in {time.time() - t:.1f}s")
    try:   # warm-up so the first real dictation is fast
        WHISPER.transcribe(np.random.default_rng(0).normal(0, 0.01, 2 * SR).astype(np.float32), SR, "en", [], "")
    except Exception as e:
        log(f"warm-up: {e}")
    set_mode("idle")
    if icon is not None:
        try:
            icon.notify(T["started"].format(a=K(CFG["dictate_key"]), b=K(CFG["dictate_translate_key"]),
                                            c=K(CFG["translate_selection_key"])), APP)
        except Exception:
            pass
    t = time.time()
    ok_t = TRANSLATOR.srv.start()
    log(f"translator {'GPU' if TRANSLATOR.srv.gpu else 'CPU'} ready={ok_t} in {time.time() - t:.1f}s")


def main():
    global icon
    log(f"--- {APP} {VERSION} starting from {engines.ROOT}")
    threading.Thread(target=worker, daemon=True).start()
    bind_hotkeys()
    icon = pystray.Icon("linart_diktat", make_icon("loading"), T["loading"], menu)
    icon.run_detached()
    threading.Thread(target=boot, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()

    root = tk.Tk()
    root.withdraw()
    popup = Popup(root, on_replace=lambda t: threading.Thread(target=lambda: (time.sleep(0.15), paste(t)), daemon=True).start(),
                  on_retranslate=lambda s, t, x, y: threading.Thread(target=run_popup_translation, args=(s, t, x, y), daemon=True).start())

    indicator = Indicator(root)

    def pump():
        STATE["ui_alive"] = time.time()
        try:
            while True:
                msg = UIQ.get_nowait()
                if msg[0] == "show":
                    popup.show(*msg[1:])
                elif msg[0] == "ind":
                    indicator.set(msg[1], msg[2])
        except queue.Empty:
            pass
        root.after(60, pump)

    root.after(60, pump)
    root.mainloop()


if __name__ == "__main__":
    main()
