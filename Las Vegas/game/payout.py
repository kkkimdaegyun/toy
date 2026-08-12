from game.money import MoneyDeck, MoneyBill
from game.config import NUM_CASINOS, MIN_CASINO_PAYOUT
from collections import defaultdict

def setup_casino_payouts(deck: MoneyDeck, rng) -> dict[int, list[MoneyBill]]:
    casinos = {}
    for i in range(1, NUM_CASINOS + 1):
        casinos[i] = []
        total = 0
        while total < MIN_CASINO_PAYOUT and deck.remaining() > 0:
            bill = deck.draw()
            casinos[i].append(bill)
            total += bill.value
    return casinos

def resolve_casino(casino_number: int, player_dice_counts: dict[str, int], bills: list[MoneyBill]) -> dict:
    counts_to_players = defaultdict(list)
    for pid, count in player_dice_counts.items():
        if count > 0:
            counts_to_players[count].append(pid)
    
    ties = []
    cancelled = []
    eligible = []
    
    for count, pids in counts_to_players.items():
        if len(pids) > 1:
            ties.append((count, pids))
            cancelled.extend(pids)
        elif len(pids) == 1:
            eligible.append((pids[0], count))
            
    eligible.sort(key=lambda x: x[1], reverse=True)
    sorted_bills = sorted(bills, key=lambda b: b.value, reverse=True)
    
    payouts = []
    unclaimed = []
    
    for i, bill in enumerate(sorted_bills):
        if i < len(eligible):
            payouts.append((eligible[i][0], bill))
        else:
            unclaimed.append(bill)
            
    return {
        'casino': casino_number,
        'counts': player_dice_counts,
        'ties': ties,
        'cancelled': cancelled,
        'eligible': eligible,
        'payouts': payouts,
        'unclaimed': unclaimed
    }

def resolve_all_casinos(casino_bills: dict[int, list[MoneyBill]], casino_dice_counts: dict[int, dict[str, int]]) -> dict:
    results = {}
    for casino in range(1, NUM_CASINOS + 1):
        bills = casino_bills.get(casino, [])
        counts = casino_dice_counts.get(casino, {})
        results[casino] = resolve_casino(casino, counts, bills)
    return results
