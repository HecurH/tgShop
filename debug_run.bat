@echo off
setlocal

:: Установка текущей директории как корневой
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Загрузка переменных из .env файла
if exist ".env" (
    for /f "usebackq delims=" %%i in (".env") do (
        set "%%i"
    )
)

:: Добавление src в PYTHONPATH
set "PYTHONPATH=%SCRIPT_DIR%"

:: Запуск основного скрипта
python src/run.py

endlocal