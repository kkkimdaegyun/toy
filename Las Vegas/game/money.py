from game.config import MONEY_DENOMINATIONS, COPIES_PER_DENOMINATION

class MoneyBill:
    def __init__(self, bill_id: str, value: int):
        self.id = bill_id
        self.value = value

    def to_dict(self):
        return {"id": self.id, "value": self.value}

class MoneyDeck:
    def __init__(self):
        self.bills = []
        bill_idx = 0
        for denom in MONEY_DENOMINATIONS:
            for _ in range(COPIES_PER_DENOMINATION):
                self.bills.append(MoneyBill(f"bill_{bill_idx}", denom))
                bill_idx += 1

    def shuffle(self, rng):
        rng.shuffle(self.bills)

    def draw(self) -> MoneyBill:
        if self.bills:
            return self.bills.pop()
        return None

    def remaining(self) -> int:
        return len(self.bills)

    def to_dict(self):
        return [bill.to_dict() for bill in self.bills]
