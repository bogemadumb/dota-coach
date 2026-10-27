import asyncio
import shutil


class Voice:
    def __init__(self, cfg: dict) -> None:
        self.engine = cfg.get("voice_engine", "say")
        self.voice_name = cfg.get("voice_name", "Milena")
        self.rate = int(cfg.get("voice_rate", 210))
        self.proc: asyncio.subprocess.Process | None = None

    @property
    def available(self) -> bool:
        return self.engine == "say" and shutil.which("say") is not None

    async def speak(self, text: str) -> None:
        if not self.available or not text:
            return
        self.proc = await asyncio.create_subprocess_exec(
            "say", "-v", self.voice_name, "-r", str(self.rate), text,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await self.proc.wait()
        self.proc = None

    def interrupt(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()


class SilentVoice:
    available = False

    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def speak(self, text: str) -> None:
        self.spoken.append(text)

    def interrupt(self) -> None:
        pass
