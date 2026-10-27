from collections import Counter

from .state import Event, GameState


class EventDetector:
    def __init__(self) -> None:
        self.prev: GameState | None = None
        self.seen_game_events: set[str] = set()

    def feed(self, state: GameState) -> list[Event]:
        prev, self.prev = self.prev, state
        out: list[Event] = []
        clock = state.clock

        def emit(kind: str, **data) -> None:
            out.append(Event(kind=kind, clock=clock, data=data))

        if prev is None or (state.match_id and state.match_id != prev.match_id):
            self.seen_game_events.clear()
            emit("match_started", match_id=state.match_id, phase=state.phase)
            prev = None

        if prev is None:
            self._game_events(state, emit)
            return out

        if state.phase != prev.phase:
            emit("phase_changed", old=prev.phase, new=state.phase)

        if state.phase in ("pregame", "game") and clock is not None and clock != prev.clock and not state.paused:
            emit("tick")

        if state.draft and prev.draft:
            for team in ("radiant", "dire"):
                for hero in state.draft.picks[team][len(prev.draft.picks[team]):]:
                    emit("hero_picked", team=team, hero=hero)
                for hero in state.draft.bans[team][len(prev.draft.bans[team]):]:
                    emit("hero_banned", team=team, hero=hero)

        if prev.alive and not state.alive:
            emit("hero_died", respawn_seconds=state.respawn_seconds)
        elif not prev.alive and state.alive:
            emit("hero_respawned")

        if prev.level > 0 and state.level > prev.level:
            emit("level_up", level=state.level)

        now, before = Counter(state.item_names()), Counter(prev.item_names())
        for name in (now - before).elements():
            emit("item_added", item=name)
        for name in (before - now).elements():
            emit("item_removed", item=name)

        self._game_events(state, emit)
        return out

    def _game_events(self, state: GameState, emit) -> None:
        for raw in state.game_events:
            key = f"{raw.get('game_time')}:{raw.get('event_type')}"
            if key in self.seen_game_events:
                continue
            self.seen_game_events.add(key)
            emit("game_event", type=raw.get("event_type"), raw=raw)
