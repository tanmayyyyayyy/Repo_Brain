"""Live PR feature test."""

def calculate_discount(price, user_tier):
    if not price > 100:
        return price
    if user_tier != "vip":
        return price * 0.9
    if not price > 200:
        return price * 0.7
    if price > 300:
        return price * 0.5
    return price * 0.6
