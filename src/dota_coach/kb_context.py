"""Knowledge for the model: mechanics digest, hero cards and item cards assembled into prompts. No network."""

import re
from functools import lru_cache
from pathlib import Path

from . import kb as kbmod
from .config import ROOT

KB_DIR = ROOT / "data" / "kb"
CARDS_DIR = KB_DIR / "cards"
DIGEST_PATH = KB_DIR / "mechanics_digest.md"
BASE_PROMPT_PATH = Path(__file__).parent / "prompts" / "brain_system.md"
CYR_RE = re.compile(r"[а-яА-ЯёЁ]")
WORD_RE = re.compile(r"[0-9a-zа-яё'’]+", re.IGNORECASE)
STOPWORDS = {
    "на", "в", "и", "с", "у", "не", "что", "как", "ли", "он", "я", "по", "для", "от", "это", "а", "но", "или", "за",
    "из", "к", "до", "при", "так", "то", "же", "ну", "мне", "его", "ее", "их", "ты", "мы", "вы", "они", "тут", "там",
    "the", "a", "of", "is", "in", "on", "to", "and", "or", "does", "do", "how", "what",
}
SKIP_ITEMS = {"tpscroll", "ultimate_scepter_2"}
MAX_ITEM_CARDS = 3
MAX_HERO_CARDS_IN_QUESTION = 2
MIN_ALIAS_CHARS = 3

SYSTEM_SECTIONS = {
    "digest": "=== Справочник механик патча 7.41f (официальные данные, главнее твоей памяти) ===",
    "me": "=== Карточка героя игрока (полная) ===",
    "allies": "=== Союзники (кратко) ===",
    "enemies": "=== Враги (кратко) ===",
}


CYR_CHARS_PER_TOKEN = 1.53
OTHER_CHARS_PER_TOKEN = 2.33


def estimate_tokens(text: str) -> int:
    """Calibrated on usage of a live Claude call (01.10.2026): real input tokens were 1.5x a 2.3/3.5 chars-per-token guess."""
    cyr = len(CYR_RE.findall(text))
    return round(cyr / CYR_CHARS_PER_TOKEN + (len(text) - cyr) / OTHER_CHARS_PER_TOKEN)


@lru_cache(maxsize=1)
def base_prompt() -> str:
    return BASE_PROMPT_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def digest() -> str:
    return DIGEST_PATH.read_text(encoding="utf-8").strip()


def kb() -> "kbmod.KB":
    return kbmod.default()


def hero_key(ref) -> str | None:
    if not ref:
        return None
    try:
        return kb().hero(ref)["key"]
    except (KeyError, FileNotFoundError):
        return None


@lru_cache(maxsize=256)
def _card(key: str, short: bool) -> str | None:
    path = CARDS_DIR / (f"{key}.short.md" if short else f"{key}.md")
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    try:
        return kb().hero_text(key, full=not short).strip()
    except (KeyError, FileNotFoundError):
        return None


def hero_card(ref, short: bool = False) -> str | None:
    key = hero_key(ref)
    return _card(key, short) if key else None


def _names_block(refs, short: bool) -> str:
    cards = []
    for ref in refs:
        card = hero_card(ref, short=short)
        if card:
            cards.append(card)
    return "\n\n".join(cards)


def system_prompt_for_draft(our_hero, allies=(), enemies=()) -> str:
    """Base brain prompt + mechanics digest + full card of our hero + short cards of everybody else."""
    parts = [base_prompt().strip(), SYSTEM_SECTIONS["digest"] + "\n" + digest()]
    mine = hero_card(our_hero)
    if mine:
        parts.append(SYSTEM_SECTIONS["me"] + "\n" + mine)
    own = hero_key(our_hero)
    ally_text = _names_block([a for a in allies if hero_key(a) != own], short=True)
    if ally_text:
        parts.append(SYSTEM_SECTIONS["allies"] + "\n" + ally_text)
    enemy_text = _names_block(enemies, short=True)
    if enemy_text:
        parts.append(SYSTEM_SECTIONS["enemies"] + "\n" + enemy_text)
    return "\n\n".join(parts) + "\n"


def _ngrams(text: str):
    words = WORD_RE.findall(text.lower().replace("ё", "е"))
    for n in (5, 4, 3, 2, 1):
        for i in range(len(words) - n + 1):
            chunk = words[i:i + n]
            if all(w in STOPWORDS for w in chunk):
                continue
            yield i, n, " ".join(chunk)


@lru_cache(maxsize=512)
def _exact(kind: str, phrase: str) -> str | None:
    if len(phrase) < MIN_ALIAS_CHARS:
        return None
    hits = kb().search(phrase, kind=kind, limit=1)
    if not hits or hits[0]["score"] < 95:
        return None
    key = hits[0]["key"]
    row = kb().index["items" if kind == "item" else "heroes"][key]
    if kind == "item" and (row.get("recipe") or key in SKIP_ITEMS):
        return None
    return key


def entities_in_text(text: str, kind: str, limit: int) -> list[str]:
    used: set[int] = set()
    found: list[str] = []
    for i, n, phrase in _ngrams(text):
        span = set(range(i, i + n))
        if span & used:
            continue
        key = _exact(kind, phrase)
        if key is None:
            continue
        used |= span
        if key not in found:
            found.append(key)
        if len(found) >= limit:
            break
    return found


def item_cards_for_keys(keys, limit: int = MAX_ITEM_CARDS) -> str:
    cards, seen = [], set()
    for ref in keys:
        try:
            key = kb().item(ref)["key"]
        except (KeyError, FileNotFoundError):
            continue
        if key in seen:
            continue
        seen.add(key)
        cards.append(kb().item_text(key))
        if len(cards) >= limit:
            break
    return "\n\n".join(cards)


def item_cards_for_text(text: str, limit: int = MAX_ITEM_CARDS) -> str:
    return item_cards_for_keys(entities_in_text(text, "item", limit), limit)


def context_for_question(text: str, hero: str | None = None) -> str:
    """Digest + hero card(s) + item cards relevant to a free-form question (used by the fact-check harness)."""
    parts = [SYSTEM_SECTIONS["digest"] + "\n" + digest()]
    own = hero_key(hero)
    named = [h for h in entities_in_text(text, "hero", MAX_HERO_CARDS_IN_QUESTION + 1) if h != own][:MAX_HERO_CARDS_IN_QUESTION]
    if own:
        card = _card(own, False)
        if card:
            parts.append(f"=== Карточка героя {own} (сводка и сборки) ===\n{card}")
    for key in ([own] if own else []) + named:
        try:
            parts.append(f"=== Официальные данные героя {key} (все числа способностей) ===\n{kb().hero_text(key)}")
        except (KeyError, FileNotFoundError):
            continue
    items = item_cards_for_text(text)
    if items:
        parts.append("=== Карточки предметов (официальные данные) ===\n" + items)
    return "\n\n".join(parts) + "\n"
