@echo off
REM Build a standalone polytime.exe.
REM Prereq (one-time):  .venv\Scripts\python.exe -m pip install -r requirements-dev.txt

set PY=.venv\Scripts\python.exe
if not exist %PY% set PY=python

%PY% -m PyInstaller --onefile --noconsole --name polytime ^
  --add-data "model;model" ^
  --add-data "transforms;transforms" ^
  --add-data "viz;viz" ^
  --add-data "score_io;score_io" ^
  --collect-submodules matplotlib.backends ^
  --hidden-import matplotlib.backends.backend_svg ^
  --hidden-import matplotlib.backends.backend_agg ^
  app.py
echo.
echo Done. See dist\polytime.exe
