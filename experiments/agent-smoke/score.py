"""Synthetic agent exercise; unrelated to the future hackathon product."""

def percentage(points, maximum):
    if not maximum > 0 or not 0 <= points <= maximum:
        raise ValueError('Expected maximum > 0 and points in [0, maximum]')
    return points / maximum * 100
