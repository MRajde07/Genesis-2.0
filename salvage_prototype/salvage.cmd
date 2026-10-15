@echo off
setlocal
set "SALVAGE_ROOT=%~dp0"
set "PYTHONPATH=%SALVAGE_ROOT%src;%PYTHONPATH%"
python -c "import sys; from salvage.cli import main; sys.exit(main(sys.argv[1:]))" %*
exit /b 0
