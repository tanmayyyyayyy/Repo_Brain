"""Live PR feature test."""

def calculate_discount(price, user_tier):
    if price > 100:
        if user_tier == "vip":
            if price > 200:
                if price > 300:
                    return price * 0.5
                else:
                    return price * 0.6
            else:
                return price * 0.7
        else:
            return price * 0.9
    else:
        return price
