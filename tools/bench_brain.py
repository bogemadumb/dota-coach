import asyncio
import statistics
import sys
import time

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, TextBlock

SYSTEM = (
    "Ты голосовой тренер по Dota 2. Отвечай по-русски одной короткой фразой до 12 слов, "
    "без вступлений. Только совет игроку."
)

PROMPTS = [
    "Мид, Shadow Fiend, 5:50, 900 золота, против Puck. Что делать?",
    "Керри, Anti-Mage, 14:00, 2100 золота, у врагов Lion и Zeus. Что покупать?",
    "Саппорт, Crystal Maiden, 8:30, враги пропали с линий: Pudge, Slark. Что делать?",
    "Оффлейн, Mars, 22:00, у врага Phantom Assassin собрала Desolator. Что покупать?",
    "Мид, Invoker, 3:55, руна силы через 5 секунд. Что делать?",
]


async def bench(model: str, rounds: int) -> None:
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM,
        model=model,
        tools=[],
        setting_sources=[],
        max_turns=1,
    )
    t0 = time.perf_counter()
    async with ClaudeSDKClient(options=options) as client:
        connect = time.perf_counter() - t0
        firsts, totals = [], []
        for i in range(rounds):
            prompt = PROMPTS[i % len(PROMPTS)]
            start = time.perf_counter()
            first = None
            text = ""
            await client.query(prompt)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            if first is None:
                                first = time.perf_counter() - start
                            text += block.text
                elif isinstance(msg, ResultMessage):
                    break
            total = time.perf_counter() - start
            firsts.append(first or total)
            totals.append(total)
            print(f"{model} #{i + 1}: first={firsts[-1]:.2f}s total={total:.2f}s | {text.strip()}", flush=True)
    print(
        f"SUMMARY {model}: connect={connect:.2f}s "
        f"median_total={statistics.median(totals):.2f}s "
        f"min={min(totals):.2f}s max={max(totals):.2f}s",
        flush=True,
    )


async def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    for model in sys.argv[2:] or ["haiku", "sonnet"]:
        await bench(model, rounds)


if __name__ == "__main__":
    asyncio.run(main())
