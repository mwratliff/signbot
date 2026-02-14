from __future__ import annotations
from pathlib import Path

# Root of the project (this file lives in root)
ROOT = Path(__file__).resolve().parent

# Folders
DICTS_DIR = ROOT / "dictionaries"
LOGS_DIR = ROOT / "logs"
DEBUG_LOGS_DIR = LOGS_DIR / "debug"
ERROR_LOGS_DIR = LOGS_DIR / "errors"
DATA_DIR = ROOT / "data"
DAILY_DIR = DATA_DIR / "daily"

# Files (daily)
DAILY_CONFIG_PATH = DAILY_DIR / "daily-task-config.json"
DAILY_HISTORY_PATH = DAILY_DIR / "daily-word-history.json"

# Files (logs)
DISCORD_LOG_PATH = ERROR_LOGS_DIR / "discord.log"
ERROR_HANDLING_LOG_PATH = ERROR_LOGS_DIR / "discord-error-handling.log"
