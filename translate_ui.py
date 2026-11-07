"""Hotkeys, local translation and the popup window for LinArt Diktat."""
from __future__ import annotations

import json
import queue
import re
import tkinter as tk
import urllib.request

UIQ: "queue.Queue" = queue.Queue()     # work for the Tk main thread
# first six = quick languages (also in tray menu)
LANGS = [("en", "English", "English"), ("ru", "Русский", "Russian"), ("de", "Deutsch", "German"),
         ("pl", "Polski", "Polish"), ("lt", "Lietuvių", "Lithuanian"), ("zh", "中文", "Simplified Chinese"),
         ("uk", "Українська", "Ukrainian"), ("fr", "Français", "French"), ("es", "Español", "Spanish"),
         ("it", "Italiano", "Italian"), ("nl", "Nederlands", "Dutch"), ("cs", "Čeština", "Czech"),
         ("tr", "Türkçe", "Turkish")]
LANG_NAMES = {c: n for c, n, _ in LANGS}
_EN = {c: e for c, _, e in LANGS}
_BY_NAME = {n: c for c, n, _ in LANGS}
_DE = re.compile(r"[äöüß]|\b(der|die|das|und|ist|nicht|ich|wir|sie|mit|für|auf|ein|eine|bitte|danke)\b", re.I)
_PL = re.compile(r"[ąćęłńśźż]|\b(jest|nie|się|dla|czy|jak|dzień|dobry|dziękuję)\b", re.I)
_LT = re.compile(r"[ėįųū]|\b(labas|ačiū|kaip|kas|yra|ir|aš|laba|diena)\b", re.I)


def detect_lang(text: str) -> str:
    if len(re.findall(r"[一-鿿]", text)) > 1:
        return "zh"
    cyr = len(re.findall(r"[а-яёіїєґА-ЯЁІЇЄҐ]", text))
    lat = len(re.findall(r"[a-zA-ZÀ-ž]", text))
    if cyr > lat * 0.3:
        return "uk" if re.search(r"[іїєґІЇЄҐ]", text) else "ru"
    if _LT.search(text):
        return "lt"
    if _PL.search(text):
        return "pl"
    return "de" if _DE.search(text) else "en"


def name(code: str) -> str:
    return LANG_NAMES.get(code, code)


def target_for(src: str, cfg: dict) -> str:          # dictation / Shift+F8 (own text)
    return cfg.get("translate_to_if_german", "ru") if src == cfg.get("translate_to", "de") else cfg.get("translate_to", "de")


def selection_target(src: str, cfg: dict) -> str:   # F8 popup (reading other people's text)
    t = cfg.get("selection_target", "ru")
    return cfg.get("selection_target_if_same", "en") if src == t else t


def translate(text: str, target: str, cfg: dict) -> str:
    body = {"model": cfg.get("llm_model_translate") or cfg.get("llm_model"), "temperature": 0.1,
            "max_tokens": min(4000, 200 + len(text) * 3), "messages": [
                {"role": "system", "content": f"You are a professional translator. Translate the user's text into {_EN.get(target, target)}. "
                 "Keep meaning, tone, names, numbers, units, emojis, line breaks and formatting. Use natural, idiomatic "
                 "language. Output ONLY the translation, no quotes, no notes."},
                {"role": "user", "content": text}]}
    req = urllib.request.Request(cfg["llm_url"] + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip().strip('"„“')


# ------------------------------------------------------------------ popup (Tk, main thread only)
class Popup:
    BG, FG, MUTED, ACC, BTN = "#1c2129", "#dde4ea", "#8b97a4", "#6cd3e6", "#242b35"

    def __init__(self, root: tk.Tk, on_replace, on_retranslate):
        self.root, self.on_replace, self.on_retranslate = root, on_replace, on_retranslate
        self.win, self.text, self.src, self.pos = None, "", "", (0, 0)

    def _build(self):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=self.BG, highlightthickness=1, highlightbackground="#2e3742")
        top = tk.Frame(w, bg=self.BG)
        top.pack(fill="x", padx=12, pady=(8, 2))
        self.hdr = tk.Label(top, bg=self.BG, fg=self.MUTED, font=("Segoe UI", 9), anchor="w")
        self.hdr.pack(side="left", fill="x", expand=True)
        self.lang = tk.StringVar(w)
        om = tk.OptionMenu(top, self.lang, *[n for _, n, _ in LANGS], command=self._pick)
        om.configure(bg=self.BTN, fg=self.FG, activebackground="#2e3742", activeforeground=self.FG,
                     relief="flat", highlightthickness=0, font=("Segoe UI", 9), cursor="hand2", padx=8)
        menu = om["menu"]
        menu.configure(bg=self.BTN, fg=self.FG, activebackground=self.ACC, activeforeground="#0d2a31",
                       font=("Segoe UI", 10))
        menu.insert_separator(6)
        tk.Label(top, text="на:", bg=self.BG, fg=self.MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(8, 4))
        om.pack(side="left")
        self.txt = tk.Text(w, bg=self.BG, fg=self.FG, font=("Segoe UI", 11), wrap="word", width=56, height=6,
                           relief="flat", insertbackground=self.FG, padx=2)
        self.txt.pack(fill="both", expand=True, padx=12, pady=(4, 0))
        bar = tk.Frame(w, bg=self.BG)
        bar.pack(fill="x", padx=12, pady=8)
        mk = lambda t, c, prim=False: tk.Button(bar, text=t, command=c, relief="flat", cursor="hand2",
                                                bg=self.ACC if prim else self.BTN, fg="#0d2a31" if prim else self.FG,
                                                activebackground=self.ACC, font=("Segoe UI", 9, "bold" if prim else "normal"), padx=10, pady=3)
        mk("Копировать", self.copy, True).pack(side="left")
        mk("Заменить выделенное", self.replace).pack(side="left", padx=6)
        mk("✕", self.close).pack(side="right")
        w.bind("<Escape>", lambda e: self.close())
        self.win = w

    def _pick(self, display_name):
        code = _BY_NAME.get(display_name)
        if code and self.src:
            self.on_retranslate(self.src, code, *self.pos)

    def show(self, x, y, header, body, busy=False, src="", target=""):
        if self.win is None or not self.win.winfo_exists():
            self._build()
        self.pos, self.src = (x, y), src or self.src
        if target:
            self.lang.set(name(target))
        self.hdr.config(text=header)
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", body)
        lines = max(2, min(16, body.count("\n") + 1 + len(body) // 60))
        self.txt.config(height=lines, fg=self.MUTED if busy else self.FG)
        self.text = "" if busy else body
        self.win.update_idletasks()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        ww, wh = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        self.win.geometry(f"+{min(max(0, x + 12), sw - ww - 8)}+{min(max(0, y + 18), sh - wh - 48)}")
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def copy(self):
        if self.text:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.text)
            self.hdr.config(text="✓ скопировано")
            self.root.after(700, self.close)

    def replace(self):
        if self.text:
            t = self.text
            self.close()
            self.on_replace(t)

    def close(self):
        if self.win is not None and self.win.winfo_exists():
            self.win.destroy()
        self.win = None
