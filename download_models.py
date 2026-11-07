"""Download the Whisper models LinArt Diktat uses (resumable, safe to re-run)."""
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
from huggingface_hub import snapshot_download  # noqa: E402

M = Path(__file__).resolve().parent / "models"
# GPU path (PyTorch / transformers)
snapshot_download("openai/whisper-large-v3-turbo", local_dir=str(M / "hf-large-v3-turbo"),
                  allow_patterns=["*.json", "*.txt", "model.safetensors"])
# CPU fallback (faster-whisper / CTranslate2)
snapshot_download("mobiuslabsgmbh/faster-whisper-large-v3-turbo", local_dir=str(M / "large-v3-turbo"))
print("models ready in", M)
