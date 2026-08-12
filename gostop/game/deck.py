"""The 20-card number deck.

0..9, two physical copies of each.  0 stands for 장 (ten).

Card ids are OPAQUE random tokens on purpose: an id is broadcast to every
client so it can animate a specific card, therefore the id must not leak the
card's number.  Never build an id from the number.
"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass

from . import config


@dataclass(frozen=True, slots=True)
class Card:
    id: str
    number: int          # 0..9   (0 == 장 / 10)

    @property
    def label(self) -> str:
        """What is printed big on the card face."""
        return str(self.number)

    @property
    def sub_label(self) -> str:
        """Small helper text under the number."""
        return "장(10)" if self.number == 0 else ""

    def public(self) -> dict:
        """Face-down representation — safe to send to anybody."""
        return {"id": self.id, "hidden": True}

    def private(self) -> dict:
        """Face-up representation — only for players allowed to see it."""
        return {
            "id": self.id,
            "hidden": False,
            "number": self.number,
            "label": self.label,
            "sub": self.sub_label,
        }


def build_deck() -> list[Card]:
    """A fresh, unshuffled 20-card deck with unique opaque ids."""
    cards = []
    used = set()
    for number in config.CARD_NUMBERS:
        for _ in range(config.COPIES_PER_NUMBER):
            while True:
                cid = secrets.token_hex(5)
                if cid not in used:
                    used.add(cid)
                    break
            cards.append(Card(id=cid, number=number))
    return cards


class Deck:
    """Server-side shoe for a single round."""

    def __init__(self, rng: random.Random | None = None):
        self._rng = rng or random.SystemRandom()
        self.cards: list[Card] = build_deck()
        self.discards: list[Card] = []
        self.shuffle()

    def shuffle(self) -> None:
        self._rng.shuffle(self.cards)

    def draw(self) -> Card:
        if not self.cards:
            raise RuntimeError("덱에 남은 카드가 없습니다.")
        return self.cards.pop()

    def draw_many(self, count: int) -> list[Card]:
        return [self.draw() for _ in range(count)]

    def discard(self, card: Card) -> None:
        self.discards.append(card)

    @property
    def remaining(self) -> int:
        return len(self.cards)


def max_players_supported() -> int:
    """Sanity guard: 6 players * 3 cards = 18 <= 20."""
    per_player = config.CARDS_FIRST_DEAL + config.CARDS_SECOND_DEAL
    return config.DECK_SIZE // per_player
