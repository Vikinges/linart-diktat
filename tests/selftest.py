"""End-to-end check of the engines: python tests/selftest.py [file.wav]"""
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import engines  # noqa: E402

wav = Path(sys.argv[1]) if len(sys.argv) > 1 else None
log = Path(__file__).resolve().parent
w = engines.Whisper(log, engines.cpu_threads())
tr = engines.Translator(log, lambda: {})
t = time.time(); print("whisper start", w.srv.start(), "gpu", w.srv.gpu, f"{time.time() - t:.1f}s", flush=True)
t = time.time(); print("translator start", tr.srv.start(), "gpu", tr.srv.gpu, f"{time.time() - t:.1f}s", flush=True)
if wav:
    with wave.open(str(wav)) as f:
        sr = f.getframerate()
        a = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768
    for _ in range(2):
        t = time.time()
        text, det = w.transcribe(a, sr, None, ["ru", "de", "en"], "WAGO, ThingsBoard")
        print(f"[{det}] {text!r} {time.time() - t:.2f}s", flush=True)
for tgt in ("ru", "de", "lt"):
    t = time.time()
    print(tgt, repr(tr.translate("Please order 20 WAGO terminals and update the ThingsBoard dashboard.", "en", tgt)),
          f"{time.time() - t:.2f}s", flush=True)
w.srv.stop()
tr.srv.stop()
