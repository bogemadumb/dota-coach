import uvicorn

from .config import load
from .server import create_app


def main() -> None:
    cfg = load()
    uvicorn.run(create_app(cfg), host=cfg["host"], port=cfg["port"], log_level="warning")
