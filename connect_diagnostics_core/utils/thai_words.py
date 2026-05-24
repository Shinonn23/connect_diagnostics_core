from pythainlp.util import num_to_thaiword


def number_to_thai_currency(amount, currency="THB"):
    amount = round(amount, 2)
    integer_part = int(amount)
    decimal_part = round((amount - integer_part) * 100)

    currency_map = {
        "THB": ("บาท", "สตางค์"),
        "USD": ("ดอลลาร์", "เซนต์"),
        "EUR": ("ยูโร", "เซนต์"),
        "JPY": ("เยน", None),  # JPY does not have a subunit
        "GBP": ("ปอนด์", "เพนนี"),
        "CNY": ("หยวน", "เฟิน"),
    }

    if currency not in currency_map:
        return num_to_thaiword(integer_part)

    main_unit, sub_unit = currency_map[currency]

    text = num_to_thaiword(integer_part) + main_unit

    if sub_unit is None:
        text += "ถ้วน"
    elif decimal_part == 0:
        text += "ถ้วน"
    else:
        text += num_to_thaiword(decimal_part) + sub_unit

    return text
