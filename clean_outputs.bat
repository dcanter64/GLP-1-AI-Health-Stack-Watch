@echo off
setlocal

set "ROOT=%~dp0"
set "OUTPUT=%ROOT%output"
set "KEEP_HISTORY=0"
set "ASSUME_YES=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--keep-history" set "KEEP_HISTORY=1"
if /I "%~1"=="/keep-history" set "KEEP_HISTORY=1"
if /I "%~1"=="--yes" set "ASSUME_YES=1"
if /I "%~1"=="/y" set "ASSUME_YES=1"
shift
goto parse_args

:args_done

if not exist "%OUTPUT%" (
    echo No output directory found at "%OUTPUT%".
    exit /b 0
)

if "%ASSUME_YES%"=="0" (
    echo This will delete generated files under "%OUTPUT%".
    if "%KEEP_HISTORY%"=="1" (
        echo Score history will be preserved.
    ) else (
        echo Score history will also be deleted.
    )
    set /p "CONFIRM=Type Y to continue: "
    if /I not "%CONFIRM%"=="Y" (
        echo Cleanup canceled.
        exit /b 0
    )
)

echo Cleaning generated output files under "%OUTPUT%"...

del /q "%OUTPUT%\reports\*.md" 2>nul
del /q "%OUTPUT%\validation\*.md" 2>nul
del /q "%OUTPUT%\classified\*.csv" 2>nul
del /q "%OUTPUT%\raw\*.json" 2>nul

if "%KEEP_HISTORY%"=="0" (
    del /q "%OUTPUT%\history\*.jsonl" 2>nul
)

if exist "%OUTPUT%\raw\cache" (
    rmdir /s /q "%OUTPUT%\raw\cache"
)

echo Cleanup complete.
endlocal
