import asyncio
import hashlib
import json

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock


def answer(say="совет", detail="потому что", priority=2, ttl=20, **extra) -> str:
    return json.dumps({"say": say, "detail": detail, "priority": priority, "ttl": ttl, **extra}, ensure_ascii=False)


def default_say(index: int) -> str:
    digest = hashlib.md5(str(index).encode()).hexdigest()
    return "".join(chr(1072 + int(ch, 16) * 2) for ch in digest[:14])


def kind_of(query: str) -> str:
    return query.split("\n", 1)[0].removeprefix("Тип запроса: ").strip()


class FakeClient:
    def __init__(self, factory) -> None:
        self.factory = factory
        self.connected = False
        self.closed = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.closed = True

    async def query(self, text: str) -> None:
        self.factory.queries.append(text)
        self.factory.owners.append(self)

    async def receive_response(self):
        f = self.factory
        f.active += 1
        f.max_active = max(f.max_active, f.active)
        try:
            if f.gate is not None:
                await f.gate.wait()
            if f.delay:
                await asyncio.sleep(f.delay)
        finally:
            f.active -= 1
        index = len(f.queries) - 1
        reply = f.replies[index] if index < len(f.replies) else answer(default_say(index))
        if callable(reply):
            reply = reply(f.queries[-1])
        if isinstance(reply, Exception):
            raise reply
        yield AssistantMessage(content=[TextBlock(text=reply)], model="fake")
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                            num_turns=1, session_id="fake")


class Factory:
    def __init__(self, replies=None, delay: float = 0.0, gate: asyncio.Event | None = None) -> None:
        self.replies = replies or []
        self.delay = delay
        self.gate = gate
        self.clients: list[FakeClient] = []
        self.options: list = []
        self.queries: list[str] = []
        self.owners: list[FakeClient] = []
        self.active = 0
        self.max_active = 0

    def __call__(self, options) -> FakeClient:
        self.options.append(options)
        client = FakeClient(self)
        self.clients.append(client)
        return client

    @property
    def kinds(self) -> list[str]:
        return [kind_of(q) for q in self.queries]
