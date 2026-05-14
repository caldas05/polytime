@echo off
REM Build a standalone polytime.exe. Requires: pip install pyinstaller
pyinstaller --onefile --noconsole --name polytime ^
  --add-data "model;model" ^
  --add-data "transforms;transforms" ^
  --add-data "viz;viz" ^
  --add-data "score_io;score_io" ^
  app.py
echo.
echo Done. See dist\polytime.exe
