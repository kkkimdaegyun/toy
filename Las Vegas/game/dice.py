class PlayerDice:
    def __init__(self, player_id: str, color: str):
        self.player_id = player_id
        self.color = color
        self.total = 8
        self.remaining = 8
        self.current_roll = []

    def roll(self, rng) -> list[int]:
        self.current_roll = rng.roll_dice(self.remaining)
        return self.current_roll

    def get_valid_casinos(self) -> list[int]:
        return list(set(self.current_roll))

    def count_matching(self, number: int) -> int:
        return self.current_roll.count(number)

    def place(self, number: int) -> int:
        count = self.count_matching(number)
        self.remaining -= count
        self.current_roll = []
        return count

    def has_dice(self) -> bool:
        return self.remaining > 0

    def to_dict(self):
        return {
            "player_id": self.player_id,
            "color": self.color,
            "total": self.total,
            "remaining": self.remaining,
            "current_roll": self.current_roll
        }
