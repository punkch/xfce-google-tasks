"""User settings from config.ini."""

import configparser

from . import paths


def load_config() -> dict:
    """Read config.ini. A missing file or key falls back to DEFAULTS."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(paths.CONFIG_PATH, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        parser = configparser.ConfigParser(interpolation=None)
    cfg = {key: parser.get("panel", key, fallback=value)
           for key, value in paths.DEFAULTS.items()}
    try:
        cfg["label"].format(count=0)
    except (KeyError, IndexError, ValueError):
        cfg["label"] = paths.DEFAULTS["label"]
    try:
        cfg["refresh"] = max(30, int(cfg["refresh"]))
    except ValueError:
        cfg["refresh"] = int(paths.DEFAULTS["refresh"])
    return cfg
