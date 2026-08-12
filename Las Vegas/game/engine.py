from game.config import *
from game.money import MoneyDeck
from game.dice import PlayerDice
from game.cards import PlayerCards
from game.payout import setup_casino_payouts, resolve_all_casinos
from game.rng import create_rng

class CasinoGame:
    def __init__(self, room_code: str, game_mode: str, seed=None):
        self.room_code = room_code
        self.game_mode = game_mode
        self.phase = LOBBY
        self.players = {}
        self.seats = [None, None, None, None]
        self.rng = create_rng(seed)
        self.money_deck = None
        self.casino_bills = {}
        self.casino_dice = {i: {} for i in range(1, NUM_CASINOS + 1)}
        self.player_dice = {}
        self.dealer_rolls = {}
        self.dealer_reroll_players = []
        self.starting_player = None
        self.current_player_idx = 0
        self.turn_order = []
        self.current_roll = []
        self.placement_sequence = 0
        self.winnings = {}
        self.won_bills = {}
        self.settlement_results = []
        
    def add_player(self, player_id: str, nickname: str, color: str, seat: int):
        self.players[player_id] = {
            'id': player_id,
            'nickname': nickname,
            'color': color,
            'seat': seat
        }
        self.seats[seat] = player_id
        self.winnings[player_id] = 0
        self.won_bills[player_id] = []
        
    def remove_player(self, player_id: str):
        if player_id in self.players:
            seat = self.players[player_id]['seat']
            self.seats[seat] = None
            del self.players[player_id]
            if player_id in self.winnings:
                del self.winnings[player_id]
            if player_id in self.won_bills:
                del self.won_bills[player_id]
            
    def start_game(self):
        self.phase = DEALER_ROLL
        # Initialize player dice/cards
        for pid, p in self.players.items():
            if self.game_mode == 'dice':
                self.player_dice[pid] = PlayerDice(pid, p['color'])
            else:
                self.player_dice[pid] = PlayerCards(pid, p['color'])
        # Create and shuffle money deck
        self.money_deck = MoneyDeck()
        self.money_deck.shuffle(self.rng)
        
    def do_dealer_roll(self):
        """Roll one die per player for starting player determination."""
        self.dealer_rolls = {}
        players_to_roll = self.dealer_reroll_players if self.dealer_reroll_players else list(self.players.keys())
        for pid in players_to_roll:
            self.dealer_rolls[pid] = self.rng.roll_die()
        return self.dealer_rolls
        
    def resolve_dealer(self):
        """Find lowest roller. Returns (winner_id, None) or (None, reroll_list)."""
        min_roll = min(self.dealer_rolls.values())
        tied_players = [pid for pid, roll in self.dealer_rolls.items() if roll == min_roll]
        
        if len(tied_players) == 1:
            self.starting_player = tied_players[0]
            self.turn_order = self.get_turn_order(tied_players[0])
            self.dealer_reroll_players = []
            self.phase = PAYOUT_SETUP
            return tied_players[0], None
        else:
            self.dealer_reroll_players = tied_players
            self.phase = DEALER_TIE_REROLL
            return None, tied_players
            
    def setup_payouts(self):
        """Deal money bills to casinos."""
        self.casino_bills = setup_casino_payouts(self.money_deck, self.rng)
        self.phase = TURN_WAITING
        return self.casino_bills
        
    def get_turn_order(self, starting_player_id: str) -> list[str]:
        """Get clockwise turn order starting from the given player."""
        filled_seats = [pid for pid in self.seats if pid is not None]
        start_idx = filled_seats.index(starting_player_id)
        return filled_seats[start_idx:] + filled_seats[:start_idx]
        
    def get_current_player(self) -> str:
        if not self.turn_order:
            return None
        return self.turn_order[self.current_player_idx]
        
    def _player_has_pieces(self, pid: str) -> bool:
        """Check if player has remaining dice/tokens."""
        pd = self.player_dice.get(pid)
        if pd is None:
            return False
        if self.game_mode == 'dice':
            return pd.has_dice()
        else:
            return pd.has_tokens()
    
    def do_roll(self):
        """Roll dice for current player."""
        pid = self.get_current_player()
        if pid is None:
            return []
        pd = self.player_dice[pid]
        if self._player_has_pieces(pid):
            if self.game_mode == 'dice':
                self.current_roll = pd.roll(self.rng)
                self.phase = DICE_ROLLING
            else:
                self.current_roll = pd.draw_cards(self.rng)
                self.phase = CARD_DRAWING
            return self.current_roll
        return []
        
    def do_card_draw(self):
        """Alias for do_roll in card mode."""
        return self.do_roll()
        
    def get_valid_casinos(self, player_id: str) -> list[int]:
        """Get valid casino selections for player's current roll."""
        pd = self.player_dice.get(player_id)
        if pd is None:
            return []
        return sorted(pd.get_valid_casinos())
    
    def get_placement_preview(self, player_id: str, casino_number: int) -> dict:
        """Preview what would happen if player places at casino."""
        pd = self.player_dice.get(player_id)
        if pd is None:
            return {}
        
        count = pd.count_matching(casino_number)
        
        # Calculate resulting counts
        resulting_counts = {}
        for pid, c in self.casino_dice[casino_number].items():
            resulting_counts[pid] = c
        resulting_counts[player_id] = resulting_counts.get(player_id, 0) + count
        
        # Check for ties
        count_groups = {}
        for pid, c in resulting_counts.items():
            if c > 0:
                if c not in count_groups:
                    count_groups[c] = []
                count_groups[c].append(pid)
        
        has_tie = False
        tie_players = []
        for c, pids in count_groups.items():
            if len(pids) > 1:
                has_tie = True
                tie_players.extend(pids)
        
        return {
            'casino': casino_number,
            'count': count,
            'resulting_counts': resulting_counts,
            'has_tie': has_tie,
            'tie_players': tie_players
        }
        
    def validate_placement(self, player_id: str, casino_number: int):
        """Validate a placement attempt. Returns (valid, error_message)."""
        if player_id != self.get_current_player():
            return False, "현재 차례가 아닙니다."
        if self.phase not in (DICE_ROLLING, CARD_DRAWING, PLACEMENT_SELECTION):
            return False, "배치할 수 없는 상태입니다."
        pd = self.player_dice.get(player_id)
        if pd is None:
            return False, "플레이어를 찾을 수 없습니다."
        valid_casinos = pd.get_valid_casinos()
        if casino_number not in valid_casinos:
            return False, "해당 숫자가 나오지 않았습니다."
        if casino_number < 1 or casino_number > 6:
            return False, "잘못된 카지노 번호입니다."
        return True, ""
        
    def do_placement(self, player_id: str, casino_number: int) -> int:
        """Place all matching dice at casino. Returns count placed."""
        pd = self.player_dice[player_id]
        count = pd.place(casino_number)
        
        if player_id not in self.casino_dice[casino_number]:
            self.casino_dice[casino_number][player_id] = 0
        self.casino_dice[casino_number][player_id] += count
        self.placement_sequence += 1
        
        self.current_roll = []
        
        # Check if round is complete
        all_done = all(not self._player_has_pieces(pid) for pid in self.turn_order)
        if all_done:
            self.phase = ROUND_COMPLETE
        else:
            self.advance_turn()
        
        return count
        
    def advance_turn(self):
        """Advance to next player who has dice."""
        for _ in range(len(self.turn_order)):
            self.current_player_idx = (self.current_player_idx + 1) % len(self.turn_order)
            pid = self.get_current_player()
            if self._player_has_pieces(pid):
                self.phase = TURN_WAITING
                return pid
        
        self.phase = ROUND_COMPLETE
        return None
        
    def do_settlement(self):
        """Resolve all 6 casinos and calculate payouts."""
        self.settlement_results = resolve_all_casinos(self.casino_bills, self.casino_dice)
        
        for casino_num in range(1, NUM_CASINOS + 1):
            res = self.settlement_results[casino_num]
            for pid, bill in res['payouts']:
                if pid in self.won_bills:
                    self.won_bills[pid].append(bill)
                    self.winnings[pid] += bill.value
                
        self.phase = GAME_OVER
        return self.settlement_results
        
    def get_winner(self):
        """Get winner(s). Returns list of player_ids with highest winnings."""
        if not self.winnings:
            return []
        max_money = max(self.winnings.values())
        return [pid for pid, amount in self.winnings.items() if amount == max_money]
    
    def get_rankings(self):
        """Get all players sorted by winnings descending."""
        ranked = sorted(self.winnings.items(), key=lambda x: x[1], reverse=True)
        rankings = []
        for rank, (pid, amount) in enumerate(ranked):
            player = self.players[pid]
            rankings.append({
                'player_id': pid,
                'nickname': player['nickname'],
                'color': player['color'],
                'total': amount,
                'rank': rank + 1
            })
        # Adjust ranks for ties
        for i in range(1, len(rankings)):
            if rankings[i]['total'] == rankings[i-1]['total']:
                rankings[i]['rank'] = rankings[i-1]['rank']
        return rankings
        
    def reset_for_rematch(self):
        """Reset game for a new round. Does NOT change players/seats."""
        self.phase = DEALER_ROLL
        self.casino_bills = {}
        self.casino_dice = {i: {} for i in range(1, NUM_CASINOS + 1)}
        self.dealer_rolls = {}
        self.dealer_reroll_players = []
        self.starting_player = None
        self.current_player_idx = 0
        self.turn_order = []
        self.current_roll = []
        self.placement_sequence = 0
        self.settlement_results = []
        
        # Reset money
        self.money_deck = MoneyDeck()
        self.money_deck.shuffle(self.rng)
        
        # Reset player winnings and dice
        for pid in self.players:
            self.winnings[pid] = 0
            self.won_bills[pid] = []
            if self.game_mode == 'dice':
                self.player_dice[pid] = PlayerDice(pid, self.players[pid]['color'])
            else:
                self.player_dice[pid] = PlayerCards(pid, self.players[pid]['color'])
        
    def get_full_state(self):
        """Get complete game state for client sync."""
        state = {
            'room_code': self.room_code,
            'game_mode': self.game_mode,
            'phase': self.phase,
            'players': self.players,
            'seats': self.seats,
            'turn_order': self.turn_order,
            'current_player_idx': self.current_player_idx,
            'current_player': self.get_current_player(),
            'starting_player': self.starting_player,
            'current_roll': self.current_roll,
            'placement_sequence': self.placement_sequence,
            'casino_bills': {
                str(k): [b.to_dict() for b in v] 
                for k, v in self.casino_bills.items()
            },
            'casino_dice': {str(k): v for k, v in self.casino_dice.items()},
            'player_dice': {k: v.to_dict() for k, v in self.player_dice.items()},
            'dealer_rolls': self.dealer_rolls,
            'dealer_reroll_players': self.dealer_reroll_players,
            'winnings': self.winnings,
            'won_bills': {
                k: [b.to_dict() for b in v] 
                for k, v in self.won_bills.items()
            },
        }
        if self.settlement_results:
            from game.serializers import settlement_to_dict
            state['settlement_results'] = {
                str(k): settlement_to_dict(v) 
                for k, v in self.settlement_results.items()
            }
        return state
        
    def get_public_state(self):
        """Get state safe to send to clients (no hidden deck info)."""
        return self.get_full_state()
