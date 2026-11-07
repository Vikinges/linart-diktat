import os, time, wave, subprocess, tempfile
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
import numpy as np, torch
from huggingface_hub import snapshot_download
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

MD = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "models" / "hf-large-v3-turbo")
snapshot_download("openai/whisper-large-v3-turbo", local_dir=MD,
                  allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "merges.txt", "vocab.json"])
wav = os.path.join(tempfile.mkdtemp(), "en.wav")
txt = "Please order twenty WAGO terminals and two cable ducts for the heat pump connection in Munich, and send the invoice to the customer by Friday."
subprocess.run(["powershell", "-NoProfile", "-Command",
                "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('{txt}'); $s.Dispose()"], check=True)
with wave.open(wav) as w:
    sr = w.getframerate(); a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
a = np.interp(np.linspace(0, len(a), int(len(a) * 16000 / sr)), np.arange(len(a)), a).astype(np.float32)

t = time.time()
proc = AutoProcessor.from_pretrained(MD)
model = AutoModelForSpeechSeq2Seq.from_pretrained(MD, torch_dtype=torch.float16).to("cuda").eval()
print(f"load {time.time()-t:.1f}s on {torch.cuda.get_device_name(0)}")

def run(audio):
    feats = proc(audio, sampling_rate=16000, return_tensors="pt").input_features.to("cuda", torch.float16)
    with torch.inference_mode():
        ids = model.generate(feats, max_new_tokens=220, num_beams=1)
    return proc.batch_decode(ids, skip_special_tokens=True)[0].strip()

for i in range(4):
    t = time.time(); out = run(a); torch.cuda.synchronize()
    print(f"run {i}: {len(a)/16000:.1f}s audio -> {time.time()-t:.2f}s | {out}")
