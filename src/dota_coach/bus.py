import asyncio


class Bus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self, maxsize: int = 1000) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, topic: str, payload) -> None:
        for q in list(self._subs):
            if q.full():
                q.get_nowait()
            q.put_nowait((topic, payload))
