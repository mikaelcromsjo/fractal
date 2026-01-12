@echo off
REM Usage: git_push.bat "version x"

IF "%~1"=="" (
    echo Commit message is required.
    echo Usage: %~n0 "your commit message"
    exit /b 1
)

git add .
git commit -m "%~1"
git push

pause
