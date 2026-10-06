# 芯选 —— 一键准备运行环境（Windows PowerShell）
# 常规环境（可 pip、可联网）：
#   pwsh -File scripts/setup_env.ps1
# 受限沙箱（本仓库实测：pip 解包 wheel 会被拒绝，报 OSError [Errno 13] Permission denied）
# 会自动退化为 scripts/fetch_deps.py，把依赖解包到 .deps，运行时用 PYTHONPATH 注入。
param([string]$Root = (Split-Path -Parent $PSScriptRoot))

$ErrorActionPreference = "Stop"
Write-Host "workspace: $Root"
& python -V

& python -m pip install -r "$Root\requirements.txt"
if ($LASTEXITCODE -eq 0) {
    Write-Host "依赖安装完成（pip 方式）"
} else {
    Write-Host "pip 安装失败，改用内置下载器解包到 .deps ..."
    & python "$Root\scripts\fetch_deps.py" --target "$Root\.deps"
    if ($LASTEXITCODE -ne 0) { throw "fetch_deps.py 也失败了，请检查网络或 PyPI 可达性" }
}

# 冒烟验证：只依赖标准库 + numpy/pandas 的最小检查
$env:PYTHONPATH = "$Root\.deps"
$env:PYTHONIOENCODING = "utf-8"
& python -c "import numpy,pandas,sklearn,flask,jieba;print('OK numpy',numpy.__version__,'| pandas',pandas.__version__,'| sklearn',sklearn.__version__,'| flask',flask.__version__,'| jieba ready')"
Write-Host "运行方式: `$env:PYTHONPATH='$Root\.deps'; python prototype\recommend.py STM32F103C8T6 --top 5"
