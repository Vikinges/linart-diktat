"""Unit checks for transcript clean-up (no engines needed): python tests/test_text.py"""
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import engines  # noqa: E402


clean = engines.clean_text


cases = {
    " который настра\nивает реле по скрипту": "который настраивает реле по скрипту",
    " реверс инж\nинирингом котла": "реверс инжинирингом котла",
    " Please order 20 WAGO terminals for the\n heat pump connection.\n": "Please order 20 WAGO terminals for the heat pump connection.",
    " его крив\nая тоже ,\n и всё": "его кривая тоже, и всё",
}
ok = True
for raw, want in cases.items():
    got = clean(raw)
    print("OK " if got == want else "BAD", repr(got))
    ok &= got == want
quiet = np.zeros(16000, np.float32)
print("hallucination filter:", engines._is_hallucination("Thank you."), engines._is_hallucination("Привет, как дела?"))
sys.exit(0 if ok else 1)
