def compute_price(amount: float, discount: float = 0.0) -> float:
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if discount < 0 or discount > 1:
        raise ValueError("discount must be between 0 and 1")
    return amount * (1 - discount)


class PriceService:
    def calculate(self, amount: float, tax: float = 0.0) -> float:
        if tax < 0:
            raise ValueError("tax must be non-negative")
        return compute_price(amount) * (1 + tax)
