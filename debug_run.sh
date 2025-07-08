#!/bin/bash

# Для локального запуска: загрузить переменные окружения из .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
  export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# Добавить src в PYTHONPATH, чтобы корректно работал импорт "from src..."
export PYTHONPATH="$SCRIPT_DIR"

# Запуск основного скрипта
python3 src/run.py