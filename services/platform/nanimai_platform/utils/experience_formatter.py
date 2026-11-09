def format_experience_months(months: int) -> str:
    if months == 0:
        return "Без опыта"

    years = months // 12
    remaining_months = months % 12

    parts = []

    if years > 0:
        if years % 10 == 1 and years % 100 != 11:
            years_word = "год"
        elif years % 10 in (2, 3, 4) and years % 100 not in (12, 13, 14):
            years_word = "года"
        else:
            years_word = "лет"
        parts.append(f"{years} {years_word}")

    if remaining_months > 0:
        if remaining_months % 10 == 1 and remaining_months % 100 != 11:
            months_word = "месяц"
        elif remaining_months % 10 in (2, 3, 4) and remaining_months % 100 not in (12, 13, 14):
            months_word = "месяца"
        else:
            months_word = "месяцев"
        parts.append(f"{remaining_months} {months_word}")

    return ", ".join(parts)
