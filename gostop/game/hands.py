"""Hand evaluator.

Only three categories exist in this custom game:

    광땡  (3+8, 1+8, 1+3)
    땡    (a pair; 0+0 is 장땡)
    끗    (everything else: (a+b) % 10)

There is deliberately NO 알리 / 독사 / 구삥 / 장삥 / 장사 / 세륙 / 암행어사 /
멍텅구리 / 구사 and NO 49파토.  4 + 9 is always 3끗.

Strength is a plain tuple ``(category, sub_rank)`` compared with ``>``:

    광땡 -> category 3, sub 3/2/1  (38 / 18 / 13)
    땡   -> category 2, sub 10 for 장땡 then 9..1
    끗   -> category 1, sub 0..9
"""

from __future__ import annotations

from dataclasses import dataclass

from .utils import josa

CAT_GWANG = 3
CAT_TTAENG = 2
CAT_KKEUT = 1

CAT_KEYS = {CAT_GWANG: "gwang", CAT_TTAENG: "ttaeng", CAT_KKEUT: "kkeut"}
CAT_LABELS = {CAT_GWANG: "광땡", CAT_TTAENG: "땡", CAT_KKEUT: "끗"}

# frozenset of the two numbers -> (sub_rank, display name)
_GWANG = {
    frozenset({3, 8}): (3, "38광땡"),
    frozenset({1, 8}): (2, "18광땡"),
    frozenset({1, 3}): (1, "13광땡"),
}


@dataclass(frozen=True, slots=True)
class Hand:
    """The evaluated result of exactly two cards."""

    name: str            # '38광땡' / '장땡' / '3끗'
    category: int        # CAT_*
    sub: int             # tie-break rank inside the category
    numbers: tuple       # the two card numbers, sorted ascending
    combo: str           # '3 + 8'
    explain: str         # one friendly Korean sentence

    @property
    def score(self) -> tuple:
        return (self.category, self.sub)

    @property
    def category_key(self) -> str:
        return CAT_KEYS[self.category]

    @property
    def category_label(self) -> str:
        return CAT_LABELS[self.category]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category_key,
            "categoryLabel": self.category_label,
            "sub": self.sub,
            "score": list(self.score),
            "numbers": list(self.numbers),
            "combo": self.combo,
            "explain": self.explain,
        }

    def __gt__(self, other):
        return self.score > other.score

    def __lt__(self, other):
        return self.score < other.score

    def __ge__(self, other):
        return self.score >= other.score

    def __le__(self, other):
        return self.score <= other.score


def _combo(a: int, b: int) -> str:
    return f"{a} + {b}"


def evaluate_numbers(a: int, b: int) -> Hand:
    """Evaluate two raw card numbers (0..9)."""
    for n in (a, b):
        if not isinstance(n, int) or not 0 <= n <= 9:
            raise ValueError(f"잘못된 카드 숫자입니다: {n!r}")

    lo, hi = (a, b) if a <= b else (b, a)
    numbers = (lo, hi)

    gwang = _GWANG.get(frozenset({a, b}))
    if gwang is not None and a != b:
        sub, name = gwang
        return Hand(
            name=name,
            category=CAT_GWANG,
            sub=sub,
            numbers=numbers,
            combo=_combo(lo, hi),
            explain=(
                f"{josa(_combo(lo, hi), '은', '는')} {name}입니다. "
                "광땡은 가장 강한 족보예요."
            ),
        )

    if a == b:
        if a == 0:
            return Hand(
                name="장땡",
                category=CAT_TTAENG,
                sub=10,
                numbers=numbers,
                combo=_combo(0, 0),
                explain="0 + 0은 장땡입니다. 0은 장(10)이라서 가장 강한 땡이에요.",
            )
        return Hand(
            name=f"{a}땡",
            category=CAT_TTAENG,
            sub=a,
            numbers=numbers,
            combo=_combo(a, a),
            explain=f"같은 숫자 두 장이라 {a}땡입니다.",
        )

    total = a + b
    value = total % 10
    return Hand(
        name=f"{value}끗",
        category=CAT_KKEUT,
        sub=value,
        numbers=numbers,
        combo=_combo(lo, hi),
        explain=(
            f"{lo} + {hi} = {josa(str(total), '이라서', '라서')} "
            f"일의 자리인 {value}끗입니다."
        ),
    )


def evaluate(cards) -> Hand:
    """Evaluate an iterable of exactly two Card objects (or ints)."""
    items = list(cards)
    if len(items) != 2:
        raise ValueError("족보는 카드 2장으로만 계산할 수 있습니다.")
    numbers = [c if isinstance(c, int) else c.number for c in items]
    return evaluate_numbers(numbers[0], numbers[1])


def compare(hand_a: Hand, hand_b: Hand) -> int:
    """-1 / 0 / 1 — classic comparator."""
    if hand_a.score == hand_b.score:
        return 0
    return 1 if hand_a.score > hand_b.score else -1


def best_of(hands) -> list:
    """Given [(key, Hand), ...] return the keys sharing the top score."""
    items = list(hands)
    if not items:
        return []
    top = max(h.score for _, h in items)
    return [k for k, h in items if h.score == top]


def preview_discards(cards) -> list[dict]:
    """For the 3-card discard screen.

    Returns one entry per discardable card:
        {'discard': card_id, 'keep': [id, id], 'keepNumbers': [a, b], 'hand': {...}}
    """
    items = list(cards)
    if len(items) != 3:
        raise ValueError("버릴 카드 미리보기는 3장일 때만 계산합니다.")
    out = []
    for i, card in enumerate(items):
        keep = [c for j, c in enumerate(items) if j != i]
        hand = evaluate(keep)
        out.append({
            "discard": card.id,
            "discardNumber": card.number,
            "keep": [c.id for c in keep],
            "keepNumbers": [c.number for c in keep],
            "hand": hand.to_dict(),
        })
    # Deliberately kept in the player's own card order — the UI shows every
    # option and lets the human choose.  We never pre-pick for them.
    return out


# --- the canonical 23-entry ranking table (also used by tests & the UI) ------

def ranking_table() -> list[dict]:
    """Every possible hand, strongest first.  Exactly 23 entries."""
    rows = [
        {"name": "38광땡", "combo": "3 + 8", "group": "gwang"},
        {"name": "18광땡", "combo": "1 + 8", "group": "gwang"},
        {"name": "13광땡", "combo": "1 + 3", "group": "gwang"},
        {"name": "장땡", "combo": "0 + 0", "group": "ttaeng"},
    ]
    for n in range(9, 0, -1):
        rows.append({"name": f"{n}땡", "combo": f"{n} + {n}", "group": "ttaeng"})
    for n in range(9, -1, -1):
        rows.append({"name": f"{n}끗", "combo": "", "group": "kkeut"})
    return rows
