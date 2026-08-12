"""Deck integrity and the 광땡 / 땡 / 끗 evaluator."""

import re
from collections import Counter

import pytest

from game import config, hands
from game.deck import Card, Deck, build_deck

# --------------------------------------------------------------------------- #
# deck
# --------------------------------------------------------------------------- #


def test_deck_has_twenty_cards_two_of_each_number():
    deck = build_deck()
    assert len(deck) == config.DECK_SIZE == 20
    counts = Counter(c.number for c in deck)
    assert counts == {n: 2 for n in range(10)}


def test_card_ids_are_unique():
    deck = build_deck()
    ids = [c.id for c in deck]
    assert len(set(ids)) == len(ids)


def test_card_ids_look_like_random_tokens():
    """An id is broadcast to everyone, so it must be a random token."""
    for card in build_deck():
        assert re.fullmatch(r"[0-9a-f]{10}", card.id), (
            "card id %r is not a random hex token" % (card.id,)
        )


def test_card_ids_are_not_derived_from_the_number():
    """Two fresh decks must not reuse ids — that proves ids carry no data.

    A derived scheme like ``n3#1`` would produce the *same* id for the same
    number every time, which is exactly the leak this guards against.
    """
    first = build_deck()
    second = build_deck()
    assert not ({c.id for c in first} & {c.id for c in second})
    by_number_first = {}
    for c in first:
        by_number_first.setdefault(c.number, []).append(c.id)
    for c in second:
        assert c.id not in by_number_first[c.number]


def test_public_view_never_carries_a_number():
    for card in build_deck():
        pub = card.public()
        assert set(pub.keys()) == {"id", "hidden"}
        assert pub["hidden"] is True
        assert "number" not in pub


def test_private_view_carries_the_number():
    card = Card(id="abc", number=7)
    priv = card.private()
    assert priv["number"] == 7
    assert priv["hidden"] is False
    assert priv["label"] == "7"
    assert priv["sub"] == ""


def test_zero_is_displayed_as_jang():
    assert Card(id="a", number=0).sub_label == "장(10)"
    assert Card(id="a", number=0).label == "0"
    for n in range(1, 10):
        assert Card(id="a", number=n).sub_label == ""


def test_deck_draw_reduces_remaining_and_preserves_composition():
    deck = Deck()
    assert deck.remaining == 20
    drawn = deck.draw_many(20)
    assert deck.remaining == 0
    assert Counter(c.number for c in drawn) == {n: 2 for n in range(10)}


def test_drawing_from_an_empty_deck_raises():
    deck = Deck()
    deck.draw_many(20)
    with pytest.raises(RuntimeError):
        deck.draw()


def test_discard_pile_collects_cards():
    deck = Deck()
    card = deck.draw()
    deck.discard(card)
    assert deck.discards == [card]


# --------------------------------------------------------------------------- #
# the nine hands the spec calls out by name
# --------------------------------------------------------------------------- #

SPEC_CASES = [
    ((3, 8), "38광땡"),
    ((1, 8), "18광땡"),
    ((1, 3), "13광땡"),
    ((0, 0), "장땡"),
    ((9, 9), "9땡"),
    ((1, 1), "1땡"),
    ((4, 9), "3끗"),
    ((9, 8), "7끗"),
    ((2, 8), "0끗"),
]


@pytest.mark.parametrize("pair,expected", SPEC_CASES)
def test_named_hands(pair, expected):
    assert hands.evaluate_numbers(*pair).name == expected


@pytest.mark.parametrize("pair,expected", SPEC_CASES)
def test_hands_are_commutative(pair, expected):
    a, b = pair
    assert hands.evaluate_numbers(a, b).score == hands.evaluate_numbers(b, a).score


def expected_name(a, b):
    """An independent implementation of the rules, written from the spec."""
    pair = frozenset({a, b})
    if a != b and pair == frozenset({3, 8}):
        return "38광땡"
    if a != b and pair == frozenset({1, 8}):
        return "18광땡"
    if a != b and pair == frozenset({1, 3}):
        return "13광땡"
    if a == b:
        return "장땡" if a == 0 else "%d땡" % a
    return "%d끗" % ((a + b) % 10)


@pytest.mark.parametrize("a", range(10))
@pytest.mark.parametrize("b", range(10))
def test_every_possible_pair(a, b):
    hand = hands.evaluate_numbers(a, b)
    assert hand.name == expected_name(a, b)
    if hand.name.endswith("광땡"):
        assert hand.category == hands.CAT_GWANG
    elif hand.name.endswith("땡"):
        assert hand.category == hands.CAT_TTAENG
    else:
        assert hand.category == hands.CAT_KKEUT


# --------------------------------------------------------------------------- #
# ordering
# --------------------------------------------------------------------------- #

# (representative cards, name) strongest first — the canonical 23.
CANONICAL = (
    [((3, 8), "38광땡"), ((1, 8), "18광땡"), ((1, 3), "13광땡"), ((0, 0), "장땡")]
    + [((n, n), "%d땡" % n) for n in range(9, 0, -1)]
    + [((9, 5), "4끗")]  # placeholder, replaced below
)


def kkeut_pair(value):
    """Two different numbers, not a 광땡 combo, summing to `value` mod 10."""
    for a in range(10):
        for b in range(a + 1, 10):
            if (a + b) % 10 != value:
                continue
            if frozenset({a, b}) in (frozenset({3, 8}), frozenset({1, 8}), frozenset({1, 3})):
                continue
            return (a, b)
    raise AssertionError("no 끗 pair for %d" % value)


CANONICAL = (
    [((3, 8), "38광땡"), ((1, 8), "18광땡"), ((1, 3), "13광땡"), ((0, 0), "장땡")]
    + [((n, n), "%d땡" % n) for n in range(9, 0, -1)]
    + [(kkeut_pair(v), "%d끗" % v) for v in range(9, -1, -1)]
)


def test_canonical_list_is_23_long():
    assert len(CANONICAL) == 23


def test_strictly_decreasing_strength():
    scores = []
    for pair, name in CANONICAL:
        hand = hands.evaluate_numbers(*pair)
        assert hand.name == name, "%s produced %s, expected %s" % (pair, hand.name, name)
        scores.append(hand.score)
    for i in range(len(scores) - 1):
        assert scores[i] > scores[i + 1], (
            "%s is not stronger than %s" % (CANONICAL[i][1], CANONICAL[i + 1][1])
        )


def test_spec_comparisons():
    ev = hands.evaluate_numbers
    assert ev(3, 8) > ev(1, 8)          # 38광땡 > 18광땡
    assert ev(1, 3) > ev(0, 0)          # 13광땡 > 장땡
    assert ev(0, 0) > ev(9, 9)          # 장땡 > 9땡
    assert ev(1, 1) > ev(4, 5)          # 1땡 > 9끗
    assert ev(4, 5) > ev(2, 6)          # 9끗 > 8끗


# --------------------------------------------------------------------------- #
# no 49파토, no traditional exceptions
# --------------------------------------------------------------------------- #

def test_four_nine_is_always_three_kkeut():
    hand = hands.evaluate_numbers(4, 9)
    assert hand.name == "3끗"
    assert hand.category == hands.CAT_KKEUT
    assert hand.score == hands.evaluate_numbers(9, 4).score


BANNED = ["49파토", "파토", "알리", "독사", "구삥", "장삥", "장사",
          "세륙", "암행어사", "멍텅구리", "구사"]


def test_no_traditional_special_hands_exist():
    names = {row["name"] for row in hands.ranking_table()}
    for banned in BANNED:
        assert banned not in names
    for a in range(10):
        for b in range(10):
            assert hands.evaluate_numbers(a, b).name not in BANNED


# --------------------------------------------------------------------------- #
# ranking table
# --------------------------------------------------------------------------- #

def test_ranking_table_matches_canonical_order():
    rows = hands.ranking_table()
    assert len(rows) == 23
    assert [r["name"] for r in rows] == [name for _pair, name in CANONICAL]


def test_ranking_table_groups():
    rows = hands.ranking_table()
    counts = Counter(r["group"] for r in rows)
    assert counts == {"gwang": 3, "ttaeng": 10, "kkeut": 10}


# --------------------------------------------------------------------------- #
# evaluate() plumbing
# --------------------------------------------------------------------------- #

def test_evaluate_accepts_cards_and_ints():
    cards = [Card(id="a", number=3), Card(id="b", number=8)]
    assert hands.evaluate(cards).name == "38광땡"
    assert hands.evaluate([3, 8]).name == "38광땡"


@pytest.mark.parametrize("bad", [[], [3], [1, 2, 3]])
def test_evaluate_requires_exactly_two(bad):
    with pytest.raises(ValueError):
        hands.evaluate(bad)


@pytest.mark.parametrize("bad", [(-1, 3), (3, 10), ("3", 8), (None, 1), (1.5, 2)])
def test_evaluate_numbers_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        hands.evaluate_numbers(*bad)


def test_compare_and_best_of():
    strong = hands.evaluate_numbers(3, 8)
    weak = hands.evaluate_numbers(2, 8)
    same = hands.evaluate_numbers(8, 3)
    assert hands.compare(strong, weak) == 1
    assert hands.compare(weak, strong) == -1
    assert hands.compare(strong, same) == 0
    assert hands.best_of([("a", strong), ("b", weak)]) == ["a"]
    assert sorted(hands.best_of([("a", strong), ("b", same)])) == ["a", "b"]
    assert hands.best_of([]) == []


def test_hand_to_dict_shape():
    d = hands.evaluate_numbers(3, 8).to_dict()
    assert d["name"] == "38광땡"
    assert d["category"] == "gwang"
    assert d["combo"] == "3 + 8"
    assert d["score"] == [3, 3]
    assert "광땡" in d["explain"]


def test_zero_zero_explains_jang():
    assert "장" in hands.evaluate_numbers(0, 0).explain


# --------------------------------------------------------------------------- #
# discard preview
# --------------------------------------------------------------------------- #

def three_cards(a, b, c):
    return [Card(id="c1", number=a), Card(id="c2", number=b), Card(id="c3", number=c)]


def test_preview_discards_389():
    preview = hands.preview_discards(three_cards(3, 8, 9))
    by_id = {e["discard"]: e for e in preview}
    assert len(preview) == 3
    assert by_id["c3"]["hand"]["name"] == "38광땡"   # drop the 9
    assert by_id["c1"]["hand"]["name"] == "7끗"      # drop the 3 -> 8+9
    assert by_id["c2"]["hand"]["name"] == "2끗"      # drop the 8 -> 3+9


def test_preview_keeps_exactly_two_and_excludes_the_discard():
    preview = hands.preview_discards(three_cards(0, 4, 5))
    for entry in preview:
        assert len(entry["keep"]) == 2
        assert entry["discard"] not in entry["keep"]
        assert len(entry["keepNumbers"]) == 2
        assert hands.evaluate(entry["keepNumbers"]).name == entry["hand"]["name"]


def test_preview_is_in_hand_order_not_sorted_by_strength():
    """The UI must not pre-pick for the player."""
    preview = hands.preview_discards(three_cards(9, 3, 8))
    assert [e["discard"] for e in preview] == ["c1", "c2", "c3"]


@pytest.mark.parametrize("count", [1, 2, 4])
def test_preview_requires_three_cards(count):
    with pytest.raises(ValueError):
        hands.preview_discards([Card(id=str(i), number=i) for i in range(count)])
