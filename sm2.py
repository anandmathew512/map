from datetime import date, timedelta


def calculate_next_review(
    rating: int,
    ease_factor: float,
    interval: int,
    repetitions: int,
) -> tuple[float, int, int, date]:
    """SM-2 spaced repetition. Rating: 1=Again, 2=Hard, 3=Good, 4=Easy."""
    quality_map = {1: 0, 2: 3, 3: 4, 4: 5}
    quality = quality_map[rating]

    if quality < 3:
        repetitions = 0
        interval = 1
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval * ease_factor)
        repetitions += 1

    ease_factor = max(
        1.3,
        ease_factor + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02),
    )
    due_date = date.today() + timedelta(days=interval)
    return ease_factor, interval, repetitions, due_date
