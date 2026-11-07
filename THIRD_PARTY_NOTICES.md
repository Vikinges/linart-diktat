# Third-party components

LinArt Diktat itself is licensed under the Apache License 2.0 (see `LICENSE`).
The Windows installer bundles the following third-party software and models, each under its own license.

| Component | Use | License |
|---|---|---|
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) (`whisper-server`, Vulkan build by [OpenWhispr](https://github.com/OpenWhispr/whisper.cpp)) | speech recognition engine | MIT |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`, Vulkan build) | translation engine | MIT |
| [OpenAI Whisper large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) (ggml q8_0 conversion from [ggerganov/whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp)) | speech model | MIT |
| [TranslateGemma 4B](https://huggingface.co/google/translategemma-4b-it) (GGUF Q4_K_M by [bullerwins](https://huggingface.co/bullerwins/translategemma-4b-it-GGUF)) | translation model | Gemma Terms of Use |
| Microsoft Visual C++ runtime (`msvcp140.dll`, `vcruntime140*.dll`, `vcomp140.dll`) | runtime for the engines | Microsoft redistributable |
| Python, numpy, Pillow, sounddevice + PortAudio, keyboard, pyperclip | application runtime | PSF, BSD, MIT-CMU, MIT |
| pystray | tray icon | LGPL-3.0 (source: https://github.com/moses-palmer/pystray) |

## Gemma notice

**Gemma is provided under and subject to the Gemma Terms of Use found at <https://ai.google.dev/gemma/terms>.**
Use of the TranslateGemma model is also subject to the Gemma Prohibited Use Policy
(<https://ai.google.dev/gemma/prohibited_use_policy>). By installing LinArt Diktat you agree to these terms for the
bundled model. The model file was not modified; it is a quantized (Q4_K_M) GGUF conversion.
