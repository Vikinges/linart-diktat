# Downloads the speech/translation engines and models into engines\ and models\ (for development and building).
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Root = Split-Path -Parent $PSScriptRoot
$Tmp = "$PSScriptRoot\downloads"
New-Item -ItemType Directory -Force $Tmp, "$Root\engines\whisper", "$Root\engines\llama", "$Root\models" | Out-Null

# pinned versions
$WhisperZip = @{ url = "https://github.com/OpenWhispr/whisper.cpp/releases/download/0.0.11/whisper-server-win32-x64-vulkan.zip";
                 sha = "24790F91E3FFB161F4C2C9D1F3F6E9D138A23898808D13741B6CDD8921258029" }
$LlamaZip   = "https://github.com/ggml-org/llama.cpp/releases/download/b12182/llama-b12182-bin-win-vulkan-x64.zip"
$Models = @(
    @{ url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q8_0.bin"; file = "ggml-large-v3-turbo-q8_0.bin" },
    @{ url = "https://huggingface.co/bullerwins/translategemma-4b-it-GGUF/resolve/main/translategemma-4b-it-Q4_K_M.gguf"; file = "translategemma-4b-it-Q4_K_M.gguf" }
)

function Get-File($url, $out, $sha) {
    if (-not (Test-Path $out)) {
        "downloading $url"
        curl.exe -L --fail --retry 5 -o $out $url
        if ($LASTEXITCODE) { throw "download failed: $url" }
    }
    if ($sha -and (Get-FileHash $out -Algorithm SHA256).Hash -ne $sha) { throw "checksum mismatch: $out" }
}

Get-File $WhisperZip.url "$Tmp\whisper.zip" $WhisperZip.sha
Expand-Archive "$Tmp\whisper.zip" "$Tmp\whisper" -Force
Copy-Item "$Tmp\whisper\*.dll" "$Root\engines\whisper" -Force
Copy-Item (Get-ChildItem "$Tmp\whisper" -Filter "whisper-server*.exe" -Recurse | Select-Object -First 1).FullName "$Root\engines\whisper\whisper-server.exe" -Force

Get-File $LlamaZip "$Tmp\llama.zip" $null
Expand-Archive "$Tmp\llama.zip" "$Tmp\llama" -Force
$ld = (Get-ChildItem "$Tmp\llama" -Recurse -Filter llama-server.exe | Select-Object -First 1).DirectoryName
Copy-Item "$ld\*" "$Root\engines\llama" -Recurse -Force

foreach ($m in $Models) { Get-File $m.url "$Root\models\$($m.file)" $null }
"engines and models ready"
