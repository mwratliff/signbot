import json
from pathlib import Path

CONFIG_PATH = Path("data/guild_config.json")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def get_guild_config(guild_id: int) -> dict | None:
    data = load_config()
    return data.get(str(guild_id))


def set_guild_config(guild_id: int, config: dict):
    data = load_config()
    data[str(guild_id)] = config
    save_config(data)