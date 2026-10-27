from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.yaml"

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 3001,
    "gsi_token": "dota-coach-local",
    "mode": "normal",
    "voice_engine": "say",
    "voice_style": "commands",
    "voice_enabled": True,
    "brain_model": "sonnet",
    "brain_interval": 60,
    "brain_max_calls": 120,
    "brain_enabled": True,
    "role": "auto",
    "brain_recycle": 20,
    "brain_timeout": 30,
    "minimap_enabled": False,
    "scout_autoclick": False,
    "scout_min_respawn": 8,
    "realtime_enabled": False,
    "dota_path": None,
    "log_raw_gsi": True,
}


def load(path: Path = CONFIG_PATH) -> dict:
    cfg = dict(DEFAULTS)
    if path.exists():
        cfg.update(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    return cfg
