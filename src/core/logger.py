import logging
from logging.handlers import TimedRotatingFileHandler

from os import getenv
import os
from pathlib import Path
import re
import shutil

from colorlog import ColoredFormatter


LOG_LEVEL = logging.INFO
LOGFORMAT = "%(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s // %(name)s - %(funcName)s: %(lineno)d [%(worker_pid)s] | %(asctime)s"

class _BaseAlignedFormatter:
    log_tail_width = 40

    def _strip_colors(self, text):
        return re.sub(r'\x1B[@-_][0-?]*[ -/]*[@-~]', '', text)

    def _align(self, base_message, record):
        tail = f"// {record.name} - {record.funcName}: {record.lineno} [{record.worker_pid}] | {record.asctime}"
        if tail in base_message:
            base_message = base_message.replace(tail, "").rstrip()
        try:
            total_width = max(shutil.get_terminal_size()[0], 160)
        except Exception:
            total_width = 120
        visible_len = len(self._strip_colors(base_message))
        space_left = max(1, total_width - visible_len - len(tail))
        return base_message + " " * space_left + tail

class AlignedColorFormatter(_BaseAlignedFormatter, ColoredFormatter):
    def format(self, record):
        base_message = super().format(record)
        return self._align(base_message, record)

class AlignedPlainFormatter(_BaseAlignedFormatter, logging.Formatter):
    def __init__(self, fmt, datefmt=None):
        # убираем цветовые теги
        fmt = fmt.replace("%(log_color)s", "").replace("%(reset)s", "")
        super().__init__(fmt, datefmt=datefmt)

    def format(self, record):
        base_message = super().format(record)
        return self._align(base_message, record)

def load_env(name: str) -> str:
    if value := getenv(name): return value
    else: raise KeyError(f"Missing {name} environment variable.")
    
logs_path = Path(load_env("LOGS_PATH"))

# Переопределяем метод namer, чтобы архивные логи были вида "18_06_25.log"
def custom_namer(default_name):
    # default_name: logs/current.log.2024-06-25_00-00-00
    import re
    if match := re.search(r'(\d{4}-\d{2}-\d{2})', default_name):
        y, m, d = match.group(1).split('-')
        short_name = f"{y[2:]}_{m}_{d}.log"
        return str(logs_path / short_name)
    return default_name

def setup_logging():
    formatter_color = AlignedColorFormatter(LOGFORMAT, datefmt="%m-%d %H:%M:%S")
    formatter_plain = AlignedPlainFormatter(LOGFORMAT, datefmt="%m-%d %H:%M:%S")


    stream = logging.StreamHandler()
    stream.setFormatter(formatter_color)
    
    logs_path.mkdir(exist_ok=True)

    # TimedRotatingFileHandler будет создавать новый файл каждый день
    file_handler = TimedRotatingFileHandler(
        filename=logs_path / "current.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False
    )
    
    file_handler.namer = custom_namer
    file_handler.setFormatter(formatter_plain)
    
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.worker_pid = os.getpid()
        return record

    logging.setLogRecordFactory(record_factory)

    logging.basicConfig(level=LOG_LEVEL, handlers=[stream, file_handler])
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)