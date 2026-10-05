@echo off
title C4D-DEMO-EVIDENCE
%SystemRoot%\System32\chcp.com 65001 >nul
cd /d "%~dp0"
echo ==== [1/2] AGENT DEMO: gemma4:e4b native function calling (local model, no cloud API) ====
python run_map_agent.py --demo-function-calling --num-ctx 2048
echo.
echo ==== [2/2] EVIDENCE: model / runtime / device / speed ====
ollama --version
echo --- model registry (ollama list) ---
ollama list | %SystemRoot%\System32\findstr.exe /C:"gemma4:e4b"
powershell -NoProfile -Command "$c=(Get-CimInstance Win32_Processor | Select-Object -First 1).Name; $g=(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -match 'NVIDIA|Radeon|Intel'} | Select-Object -First 1).Name; $r=[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1); $o=(Get-CimInstance Win32_OperatingSystem).Caption; Write-Output ('CPU   : ' + $c); Write-Output ('GPU   : ' + $g); Write-Output ('RAM   : ' + $r + ' GB'); Write-Output ('OS    : ' + $o)"
echo NOTE  : offload = auto (Ollama decides GPU layers); ctx = 2048; tok/s above = eval_count/eval_duration
echo ==== demo finished - window kept open for screenshot ====
pause >nul
