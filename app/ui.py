"""Languages, UI strings and the translation popup for LinArt Diktat."""
from __future__ import annotations

import ctypes
import queue
import re
import tkinter as tk

UIQ: "queue.Queue" = queue.Queue()     # work for the Tk main thread

# (code, native name, English name). The first six are the quick languages.
LANGS = [("en", "English", "English"), ("ru", "Русский", "Russian"), ("de", "Deutsch", "German"),
         ("pl", "Polski", "Polish"), ("lt", "Lietuvių", "Lithuanian"), ("zh", "中文", "Chinese"),
         ("uk", "Українська", "Ukrainian"), ("fr", "Français", "French"), ("es", "Español", "Spanish"),
         ("it", "Italiano", "Italian"), ("nl", "Nederlands", "Dutch"), ("cs", "Čeština", "Czech"),
         ("tr", "Türkçe", "Turkish"), ("pt", "Português", "Portuguese"), ("ja", "日本語", "Japanese")]
LANG_NAMES = {c: n for c, n, _ in LANGS}
EN_NAMES = {c: e for c, _, e in LANGS}
_BY_NAME = {n: c for c, n, _ in LANGS}

_DE = re.compile(r"[äöüß]|\b(der|die|das|und|ist|nicht|ich|wir|sie|mit|für|auf|ein|eine|bitte|danke)\b", re.I)
_PL = re.compile(r"[ąćęłńśźż]|\b(jest|nie|się|dla|czy|jak|dzień|dobry|dziękuję)\b", re.I)
_LT = re.compile(r"[ėįųū]|\b(labas|ačiū|kaip|kas|yra|ir|aš|laba|diena)\b", re.I)
_FR = re.compile(r"\b(le|la|les|est|et|je|vous|nous|pour|avec|merci|bonjour)\b|[àâçèêëîïôûœ]", re.I)
_ES = re.compile(r"\b(el|los|las|es|y|yo|usted|para|con|gracias|hola|qué)\b|[ñ¿¡]", re.I)


def detect_lang(text: str) -> str:
    """Cheap script/keyword language guess for selected text."""
    if len(re.findall(r"[぀-ヿ]", text)) > 1:
        return "ja"
    if len(re.findall(r"[一-鿿]", text)) > 1:
        return "zh"
    cyr = len(re.findall(r"[а-яёіїєґА-ЯЁІЇЄҐ]", text))
    lat = len(re.findall(r"[a-zA-ZÀ-ž]", text))
    if cyr > lat * 0.3:
        return "uk" if re.search(r"[іїєґІЇЄҐ]", text) else "ru"
    for code, rx in (("lt", _LT), ("pl", _PL), ("de", _DE), ("fr", _FR), ("es", _ES)):
        if rx.search(text):
            return code
    return "en"


def name(code: str) -> str:
    return LANG_NAMES.get(code, code)


# ------------------------------------------------------------------ UI language (follows Windows)
def ui_lang() -> str:
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x19: "ru", 0x07: "de", 0x22: "ru"}.get(lid, "en")
    except Exception:
        return "en"


S = {
    "en": dict(ready="LinArt Diktat — ready", rec="LinArt Diktat — recording…", busy="LinArt Diktat — working…",
               loading="LinArt Diktat — loading models…",
               hk1="Dictate: hold {a}  ·  dictate + translate: hold {b}", hk2="Translate selection: {a}  ·  replace: {b}",
               always="Always translate dictation", speech="Speech language", auto="Automatic",
               dict_to="Translate dictation to", sel_to="Translate selected text ({k}) to",
               same_to="If already in that language, translate to", beep="Sounds",
               autostart="Start with Windows", again="Paste last text again", log="Log file", quit="Quit",
               copy="Copy", replace="Replace selection", to="to:", copied="✓ copied", translating="translating…",
               error="Translation error",
               started="Ready. Hold {a} to dictate, {b} to dictate + translate; select text and press {c} to translate.",
               running="LinArt Diktat is already running (see the tray).",
               ind_rec="Listening…", ind_rec_tr="Listening… (will translate)", ind_busy="Recognising…",
               ind_tr="Translating…", indicator="Show recording indicator"),
    "ru": dict(ready="LinArt Diktat — готов", rec="LinArt Diktat — запись…", busy="LinArt Diktat — обработка…",
               loading="LinArt Diktat — загрузка моделей…",
               hk1="Диктовка: держать {a}  ·  с переводом: держать {b}", hk2="Перевод выделенного: {a}  ·  заменить: {b}",
               always="Всегда переводить диктовку", speech="Язык речи", auto="Автоматически",
               dict_to="Диктовку переводить на", sel_to="Выделенный текст ({k}) переводить на",
               same_to="Если уже на этом языке — переводить на", beep="Звуковые сигналы",
               autostart="Запускать вместе с Windows", again="Вставить последний текст ещё раз", log="Журнал",
               quit="Выход", copy="Копировать", replace="Заменить выделенное", to="на:", copied="✓ скопировано",
               translating="перевожу…", error="Ошибка перевода",
               started="Готово. Держите {a} — диктовка, {b} — диктовка с переводом; выделите текст и нажмите {c} — перевод.",
               running="LinArt Diktat уже запущен (значок в трее).",
               ind_rec="Говорите…", ind_rec_tr="Говорите… (с переводом)", ind_busy="Распознаю…",
               ind_tr="Перевожу…", indicator="Показывать индикатор записи"),
    "de": dict(ready="LinArt Diktat — bereit", rec="LinArt Diktat — Aufnahme…", busy="LinArt Diktat — verarbeite…",
               loading="LinArt Diktat — lade Modelle…",
               hk1="Diktieren: {a} halten  ·  mit Übersetzung: {b} halten", hk2="Markierung übersetzen: {a}  ·  ersetzen: {b}",
               always="Diktat immer übersetzen", speech="Sprache", auto="Automatisch",
               dict_to="Diktat übersetzen nach", sel_to="Markierten Text ({k}) übersetzen nach",
               same_to="Falls schon in dieser Sprache, übersetzen nach", beep="Töne",
               autostart="Mit Windows starten", again="Letzten Text erneut einfügen", log="Protokoll", quit="Beenden",
               copy="Kopieren", replace="Markierung ersetzen", to="nach:", copied="✓ kopiert", translating="übersetze…",
               error="Übersetzungsfehler",
               started="Bereit. {a} halten = diktieren, {b} halten = diktieren + übersetzen; Text markieren + {c} = übersetzen.",
               running="LinArt Diktat läuft bereits (siehe Infobereich).",
               ind_rec="Sprechen Sie…", ind_rec_tr="Sprechen Sie… (mit Übersetzung)", ind_busy="Erkenne…",
               ind_tr="Übersetze…", indicator="Aufnahme-Anzeige einblenden"),
}
T = S[ui_lang()]


# ------------------------------------------------------------------ recording indicator (Tk, main thread only)
class Indicator:
    """Small pill at the bottom centre of the screen. Never takes focus, clicks pass through."""
    COLORS = {"rec": "#e24343", "busy": "#f0a24a", "tr": "#6cd3e6"}

    def __init__(self, root: tk.Tk):
        w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.93)
        w.configure(bg="#1c2129", highlightthickness=1, highlightbackground="#2e3742")
        self.dot = tk.Label(w, text="●", bg="#1c2129", fg="#e24343", font=("Segoe UI", 14))
        self.dot.pack(side="left", padx=(14, 6), pady=6)
        self.lbl = tk.Label(w, bg="#1c2129", fg="#dde4ea", font=("Segoe UI", 11))
        self.lbl.pack(side="left", padx=(0, 16), pady=6)
        w.withdraw()
        self.w, self.root, self.blink, self.mode = w, root, False, "idle"
        w.update_idletasks()
        try:
            u = ctypes.windll.user32
            self.hwnd = u.GetParent(w.winfo_id())
            # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOPMOST
            u.SetWindowLongW(self.hwnd, -20, u.GetWindowLongW(self.hwnd, -20) | 0x08000000 | 0x80 | 0x20 | 0x80000 | 0x8)
        except Exception:
            self.hwnd = None

    def set(self, mode: str, text: str = ""):
        self.mode = mode
        if mode == "idle":
            self.w.withdraw()
            return
        self.dot.config(fg=self.COLORS.get(mode, "#e24343"))
        self.lbl.config(text=text)
        self.w.update_idletasks()
        sw, sh = self.w.winfo_screenwidth(), self.w.winfo_screenheight()
        ww, wh = self.w.winfo_reqwidth(), self.w.winfo_reqheight()
        self.w.geometry(f"+{(sw - ww) // 2}+{sh - wh - 90}")
        if self.hwnd:
            ctypes.windll.user32.ShowWindow(self.hwnd, 4)          # SW_SHOWNOACTIVATE
            ctypes.windll.user32.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0, 0x1 | 0x2 | 0x10)   # topmost, no move/size/activate
        else:
            self.w.deiconify()
        if mode == "rec" and not self.blink:
            self.blink = True
            self._tick(True)

    def _tick(self, on: bool):
        if self.mode != "rec":
            self.blink = False
            return
        self.dot.config(fg="#e24343" if on else "#5a2020")
        self.root.after(500, self._tick, not on)


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
        tk.Label(top, text=T["to"], bg=self.BG, fg=self.MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(8, 4))
        om.pack(side="left")
        self.txt = tk.Text(w, bg=self.BG, fg=self.FG, font=("Segoe UI", 11), wrap="word", width=56, height=6,
                           relief="flat", insertbackground=self.FG, padx=2)
        self.txt.pack(fill="both", expand=True, padx=12, pady=(4, 0))
        bar = tk.Frame(w, bg=self.BG)
        bar.pack(fill="x", padx=12, pady=8)

        def mk(t, c, prim=False):
            return tk.Button(bar, text=t, command=c, relief="flat", cursor="hand2",
                             bg=self.ACC if prim else self.BTN, fg="#0d2a31" if prim else self.FG,
                             activebackground=self.ACC, font=("Segoe UI", 9, "bold" if prim else "normal"),
                             padx=10, pady=3)
        mk(T["copy"], self.copy, True).pack(side="left")
        mk(T["replace"], self.replace).pack(side="left", padx=6)
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
            self.hdr.config(text=T["copied"])
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
