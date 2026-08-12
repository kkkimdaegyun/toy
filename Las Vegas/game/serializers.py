def bill_to_dict(bill):
    if bill is None: return None
    return bill.to_dict()

def casino_state_to_dict(casino_num, bills, dice_counts):
    return {
        'casino': casino_num,
        'bills': [bill_to_dict(b) for b in bills],
        'dice': dice_counts
    }

def player_state_to_dict(player):
    return player.to_dict()

def game_state_to_dict(game):
    return game.get_public_state()

def settlement_to_dict(result):
    return {
        'casino': result['casino'],
        'counts': result['counts'],
        'ties': result['ties'],
        'cancelled': result['cancelled'],
        'eligible': result['eligible'],
        'payouts': [(pid, bill_to_dict(b)) for pid, b in result['payouts']],
        'unclaimed': [bill_to_dict(b) for b in result['unclaimed']]
    }
