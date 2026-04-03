from service import PriceService


def get_price(amount: float) -> float:
    # TODO: move SQL usage to repository
    sql = "SELECT price FROM products WHERE amount = ?"
    service = PriceService()
    calculated = service.calculate(amount, tax=0.19)
    return calculated
