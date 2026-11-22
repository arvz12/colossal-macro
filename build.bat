@echo off
rem Builds "dist\Colossal Macro.exe" (one file, no console). Needs Python with:
rem   python -m pip install pyinstaller opencv-python numpy pillow winrt-runtime winrt-Windows.Media.Ocr
rem   winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams winrt-Windows.Foundation
rem   winrt-Windows.Foundation.Collections winrt-Windows.Globalization
cd /d "%~dp0"
python make_icon.py || goto :error
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "Colossal Macro" ^
  --icon "assets\icon.ico" ^
  --version-file version_info.txt ^
  --add-data "assets;assets" ^
  --add-data "HOW TO USE.txt;." ^
  --collect-submodules winrt --hidden-import build_optimiser ^
  --exclude-module matplotlib --exclude-module scipy --exclude-module pandas ^
  --exclude-module IPython --exclude-module pytest ^
  colossal_macro.py || goto :error
copy /y "HOW TO USE.txt" "dist\HOW TO USE.txt" >nul
call :cleanup
echo.
echo Done: dist\Colossal Macro.exe
exit /b 0
:error
call :cleanup
echo Build failed.
exit /b 1
:cleanup
rem PyInstaller's work folder, spec file and Python's cache are rebuilt every time - don't leave them around.
if exist "build" rmdir /s /q "build"
if exist "Colossal Macro.spec" del /q "Colossal Macro.spec"
if exist "__pycache__" rmdir /s /q "__pycache__"
exit /b 0
