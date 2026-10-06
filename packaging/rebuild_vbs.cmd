@echo off
REM Regenerate the ANSI/GBK copy of the silent launcher.
REM VBScript hosts read .vbs as ANSI (GBK on zh-CN), so the shipped file must be GBK.
REM Edit packaging\silent_launch_utf8.vbs and run this script after any change,
REM otherwise Chinese characters in the launcher turn into mojibake.
setlocal
set "PY=%DSH_PYTHON%"
if not defined PY set "PY=python"
"%PY%" "%~dp0..\scripts\make_vbs_gbk.py" "%~dp0silent_launch_utf8.vbs"
