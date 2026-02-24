from os import getenv


def load_env(name: str, default: str = None) -> str:
    if value := getenv(name): return value
    elif default: return default
    else: raise KeyError(f"Missing {name} environment variable.")
    

BOT_TOKEN = load_env("BOT_TOKEN")

USE_WEBHOOK = load_env("USE_WEBHOOK", "0") == "1"

APP_SERVER = load_env("APP_SERVER", "aiohttp")
WORKERS = int(load_env("WORKERS", "1"))

WEB_SERVER_HOST = load_env('WEB_SERVER_HOST', "0.0.0.0")
WEB_SERVER_PORT = int(load_env('WEB_SERVER_PORT', "80"))

BASE_WEBHOOK_URL = load_env("BASE_WEBHOOK_URL")
WEBHOOK_PATH = load_env("WEBHOOK_PATH", "/webhook")
WEBHOOK_SECRET = load_env("WEBHOOK_SECRET")

CRYPTO_KEY = load_env("CRYPTO_KEY")
PROVIDER_TOKEN = load_env("PROVIDER_TOKEN")

MONGO_URI = load_env("MONGO_URI")
MONGO_TLS_CA_PATH = load_env("MONGO_TLS_CA_PATH")
MONGO_TLS_KEY_PATH = load_env("MONGO_TLS_KEY_PATH")
MEDIA_PATH = load_env("MEDIA_PATH")
CONFIGS_PATH = load_env("CONFIGS_PATH")
LOGS_PATH = load_env("LOGS_PATH")

TG_LOGS_CHANNEL_ID = load_env("TG_LOGS_CHANNEL_ID")
TG_ADMIN_CHAT_ID = load_env("TG_ADMIN_CHAT_ID")

DEBUG = load_env("DEBUG", "0") == "1"

__all__ = [
    "BOT_TOKEN",
    "USE_WEBHOOK",
    "APP_SERVER",
    "WORKERS",
    "WEB_SERVER_HOST",
    "WEB_SERVER_PORT",
    "BASE_WEBHOOK_URL",
    "WEBHOOK_PATH",
    "WEBHOOK_SECRET",
    "CRYPTO_KEY",
    "PROVIDER_TOKEN",
    "MONGO_URI",
    "MONGO_TLS_CA_PATH",
    "MONGO_TLS_KEY_PATH",
    "MEDIA_PATH",
    "CONFIGS_PATH",
    "LOGS_PATH",
    "TG_LOGS_CHANNEL_ID",
    "TG_ADMIN_CHAT_ID",
    "DEBUG"
]