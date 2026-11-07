"""Local speech-to-text (whisper.cpp) and translation (llama.cpp + TranslateGemma) engines.

Both run as hidden child processes bound to 127.0.0.1 on free ports and are tied to this
process with a Windows Job Object, so they always die together with the app.
GPU acceleration via Vulkan (AMD, NVIDIA, Intel); falls back to CPU automatically.
"""
from __future__ import annotations

import ctypes
import io
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ui import EN_NAMES


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent      # repo root in development


ROOT = app_dir()
ENGINES = ROOT / "engines"
MODELS = ROOT / "models"
WHISPER_EXE = ENGINES / "whisper" / "whisper-server.exe"
LLAMA_EXE = ENGINES / "llama" / "llama-server.exe"
WHISPER_MODEL = MODELS / "ggml-large-v3-turbo-q8_0.bin"
TRANSLATE_MODEL = MODELS / "translategemma-4b-it-Q4_K_M.gguf"
NO_WINDOW = 0x08000000

WHISPER_NAMES = {"english": "en", "russian": "ru", "german": "de", "polish": "pl", "lithuanian": "lt",
                 "chinese": "zh", "ukrainian": "uk", "french": "fr", "spanish": "es", "italian": "it",
                 "dutch": "nl", "czech": "cs", "turkish": "tr", "portuguese": "pt", "japanese": "ja"}


# ---------------------------------------------------------------- child-process lifetime
class _Job:
    def __init__(self):
        self.h = None
        try:
            k32 = ctypes.windll.kernel32
            k32.CreateJobObjectW.restype = ctypes.c_void_p

            class BASIC(ctypes.Structure):
                _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", ctypes.c_uint32),
                            ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", ctypes.c_uint32),
                            ("f", ctypes.c_size_t), ("g", ctypes.c_uint32), ("h", ctypes.c_uint32)]

            class EXT(ctypes.Structure):
                _fields_ = [("Basic", BASIC), ("Io", ctypes.c_uint64 * 6), ("p", ctypes.c_size_t),
                            ("j", ctypes.c_size_t), ("pp", ctypes.c_size_t), ("pj", ctypes.c_size_t)]
            info = EXT()
            info.Basic.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            h = k32.CreateJobObjectW(None, None)
            k32.SetInformationJobObject(ctypes.c_void_p(h), 9, ctypes.byref(info), ctypes.sizeof(info))
            self.h = h
        except Exception:
            pass

    def add(self, proc: subprocess.Popen):
        if self.h:
            try:
                ctypes.windll.kernel32.AssignProcessToJobObject(ctypes.c_void_p(self.h), ctypes.c_void_p(int(proc._handle)))
            except Exception:
                pass


JOB = _Job()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait(url: str, proc: subprocess.Popen, seconds: float) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return True
        except Exception:
            time.sleep(0.3)
    return False


class Server:
    def __init__(self, name: str, args: list[str], health: str, log_dir: Path, cpu_args: list[str]):
        self.name, self.args, self.health, self.cpu_args = name, args, health, cpu_args
        self.log = log_dir / f"{name}.log"
        self.port = 0
        self.proc: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.gpu = True

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout: float = 240) -> bool:
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return True
            for extra, gpu in (([], True), (self.cpu_args, False)):    # Vulkan first, then CPU fallback
                self.port = _free_port()
                cmd = self.args + ["--host", "127.0.0.1", "--port", str(self.port)] + extra
                self.proc = subprocess.Popen(cmd, stdout=open(self.log, "wb"), stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, cwd=str(Path(cmd[0]).parent))
                JOB.add(self.proc)
                if _wait(self.url + self.health, self.proc, timeout):
                    self.gpu = gpu
                    return True
                try:
                    self.proc.kill()
                except Exception:
                    pass
            return False

    def ensure(self) -> None:
        if not (self.proc and self.proc.poll() is None):
            if not self.start():
                raise RuntimeError(f"{self.name} engine failed to start (see {self.log})")

    def stop(self):
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass


# ---------------------------------------------------------------- speech to text
def _wav_bytes(audio: np.ndarray, sr: int) -> bytes:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return b.getvalue()


def _multipart(fields: dict, wav: bytes) -> tuple[bytes, str]:
    bnd = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.append(f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
               f'Content-Type: audio/wav\r\n\r\n'.encode() + wav + b"\r\n")
    out.append(f"--{bnd}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={bnd}"


class Whisper:
    def __init__(self, log_dir: Path, threads: int):
        self.srv = Server("whisper", [str(WHISPER_EXE), "-m", str(WHISPER_MODEL), "-l", "auto", "-t", str(threads)],
                          "/", log_dir, ["-ng"])

    def _call(self, wav: bytes, lang: str, prompt: str) -> dict:
        body, ctype = _multipart({"temperature": "0.0", "response_format": "verbose_json",
                                  "language": lang, "prompt": prompt}, wav)
        req = urllib.request.Request(self.srv.url + "/inference", data=body, headers={"Content-Type": ctype})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())

    def transcribe(self, audio: np.ndarray, sr: int, lang: Optional[str], allowed: list[str], prompt: str) -> tuple[str, str]:
        self.srv.ensure()
        wav = _wav_bytes(audio, sr)
        j = self._call(wav, lang or "auto", prompt)
        raw = str(j.get("detected_language") or j.get("language") or "").lower()
        det = WHISPER_NAMES.get(raw, raw)
        if not lang and allowed and det not in allowed:
            # auto-detect picked a language the user never speaks -> use the most likely allowed one
            probs = j.get("language_probabilities") or {}
            best = max(allowed, key=lambda c: probs.get(c, 0.0))
            j = self._call(wav, best, prompt)
            det = best
        # whisper-server puts a newline between segments; a segment can end in the middle of a word,
        # the next one then starts WITHOUT a space -> join with "" (never with " ") and tidy spaces.
        text = clean_text(str(j.get("text", "")))
        rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
        if rms < 0.012 and _is_hallucination(text):
            text = ""
        return text, det or (lang or "")


def clean_text(raw: str) -> str:
    """Join whisper-server segments (newline-separated, may split inside a word) into one clean line."""
    text = re.sub(r"[ \t]{2,}", " ", raw.replace("\r", "").replace("\n", "")).strip()
    return re.sub(r"\s+([,.!?;:])", r"\1", text)


# Whisper's typical "phantom" outputs on silence / breathing / keyboard noise
_HALLU = {"thank you", "thank you.", "thanks for watching", "thanks for watching!", "you", "bye", "bye.",
          "спасибо", "спасибо.", "спасибо за внимание", "спасибо за внимание.", "продолжение следует...",
          "продолжение следует", "субтитры сделал dimatorzok", "редактор субтитров а.семкин корректор а.егорова",
          "vielen dank.", "vielen dank", "untertitel im auftrag des zdf, 2017", "untertitel der amara.org-community",
          "...", "."}


def _is_hallucination(text: str) -> bool:
    t = text.strip().lower()
    return not t or t in _HALLU or "субтитр" in t or "untertitel" in t or "amara.org" in t


# Short sentence in the speaker's language with clean punctuation: Whisper copies the style of the prompt.
# (whisper.cpp detects the language from the audio only, so this does not bias language detection.)
STYLE_PROMPT = {
    "ru": "Хорошо, давайте обсудим это. Вот что я думаю: сначала проверим настройки, а потом всё протестируем.",
    "de": "Gut, lassen Sie uns das besprechen. Ich denke, wir prüfen zuerst die Einstellungen und testen dann alles.",
    "en": "Okay, let's discuss this. Here is what I think: we check the settings first, and then we test everything.",
    "pl": "Dobrze, omówmy to. Uważam, że najpierw sprawdzimy ustawienia, a potem wszystko przetestujemy.",
    "lt": "Gerai, aptarkime tai. Manau, kad pirmiausia patikrinsime nustatymus, o tada viską išbandysime.",
    "uk": "Добре, давайте обговоримо це. Ось що я думаю: спочатку перевіримо налаштування, а потім усе протестуємо.",
}


# ---------------------------------------------------------------- translation
class Translator:
    def __init__(self, log_dir: Path, external: Callable[[], dict]):
        self.external = external      # returns cfg; if cfg["translator_url"] is set, use that OpenAI server
        self.srv = Server("translate", [str(LLAMA_EXE), "-m", str(TRANSLATE_MODEL), "-ngl", "99", "-c", "4096",
                                        "--no-warmup"], "/health", log_dir, ["-ngl", "0"])

    def translate(self, text: str, src: str, tgt: str) -> str:
        cfg = self.external()
        if cfg.get("translator_url"):
            return _openai_translate(text, tgt, cfg)
        self.srv.ensure()
        if src == tgt or src not in EN_NAMES:
            src = "en" if tgt != "en" else "de"     # unknown source: the model copes, the label only guides it
        S, T = EN_NAMES[src], EN_NAMES[tgt]
        prompt = (f"<start_of_turn>user\nYou are a professional {S} ({src}) to {T} ({tgt}) translator. Your goal is to "
                  f"accurately convey the meaning and nuances of the original {S} text while adhering to {T} grammar, "
                  f"vocabulary, and cultural sensitivities.\nProduce only the {T} translation, without any additional "
                  f"explanations or commentary. Please translate the following {S} text into {T}:\n\n\n"
                  f"{text.strip()}<end_of_turn>\n<start_of_turn>model\n")
        body = {"prompt": prompt, "n_predict": min(2048, 64 + len(text) * 3), "temperature": 0,
                "cache_prompt": True, "stop": ["<end_of_turn>"]}
        req = urllib.request.Request(self.srv.url + "/completion", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())["content"].strip()


def _openai_translate(text: str, tgt: str, cfg: dict) -> str:
    body = {"model": cfg.get("translator_model", ""), "temperature": 0.1, "messages": [
        {"role": "system", "content": f"Translate the user's text into {EN_NAMES.get(tgt, tgt)}. Keep meaning, tone, "
         "names, numbers and formatting. Output ONLY the translation."},
        {"role": "user", "content": text}]}
    req = urllib.request.Request(cfg["translator_url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


def cpu_threads() -> int:
    return max(4, min(8, (os.cpu_count() or 8) // 2))
