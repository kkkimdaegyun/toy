from game.payout import resolve_casino
from game.money import MoneyBill

def test_payout_no_ties():
    counts = {'p1': 4, 'p2': 2, 'p3': 1}
    bills = [MoneyBill('1', 50000), MoneyBill('2', 20000)]
    res = resolve_casino(1, counts, bills)
    
    assert res['cancelled'] == []
    assert len(res['payouts']) == 2
    assert res['payouts'][0][0] == 'p1'
    assert res['payouts'][1][0] == 'p2'
    assert len(res['unclaimed']) == 0

def test_payout_simple_tie():
    counts = {'p1': 4, 'p2': 4, 'p3': 1}
    bills = [MoneyBill('1', 50000), MoneyBill('2', 20000)]
    res = resolve_casino(1, counts, bills)
    
    assert 'p1' in res['cancelled']
    assert 'p2' in res['cancelled']
    assert len(res['payouts']) == 1
    assert res['payouts'][0][0] == 'p3'
    assert res['payouts'][0][1].value == 50000
    assert len(res['unclaimed']) == 1

def test_payout_partial_tie():
    counts = {'p1': 4, 'p2': 3, 'p3': 3, 'p4': 2}
    bills = [MoneyBill('1', 50000), MoneyBill('2', 20000)]
    res = resolve_casino(1, counts, bills)
    
    assert set(res['cancelled']) == {'p2', 'p3'}
    assert len(res['payouts']) == 2
    assert res['payouts'][0][0] == 'p1'
    assert res['payouts'][1][0] == 'p4'

def test_payout_all_cancelled():
    counts = {'p1': 4, 'p2': 4, 'p3': 2, 'p4': 2}
    bills = [MoneyBill('1', 50000)]
    res = resolve_casino(1, counts, bills)
    
    assert set(res['cancelled']) == {'p1', 'p2', 'p3', 'p4'}
    assert len(res['payouts']) == 0
    assert len(res['unclaimed']) == 1

def test_payout_extra_bills():
    counts = {'p1': 2}
    bills = [MoneyBill('1', 50000), MoneyBill('2', 20000)]
    res = resolve_casino(1, counts, bills)
    
    assert len(res['payouts']) == 1
    assert res['payouts'][0][0] == 'p1'
    assert len(res['unclaimed']) == 1
