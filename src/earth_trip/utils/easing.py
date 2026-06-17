import math


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2


def ease_out_quad(t: float) -> float:
    return 1 - (1 - t) ** 2


def ease_in_quad(t: float) -> float:
    return t * t


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smoothstep(t: float) -> float:
    return t * t * (3 - 2 * t)
