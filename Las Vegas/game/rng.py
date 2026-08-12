import random
import secrets

class GameRNG:
    def __init__(self, rng_backend):
        self.rng = rng_backend
        
    def roll_die(self) -> int:
        return self.rng.randint(1, 6)
        
    def roll_dice(self, count: int) -> list[int]:
        return [self.roll_die() for _ in range(count)]
        
    def shuffle(self, lst: list) -> None:
        self.rng.shuffle(lst)

def create_rng(seed=None) -> GameRNG:
    if seed is None:
        return GameRNG(secrets.SystemRandom())
    return GameRNG(random.Random(seed))
