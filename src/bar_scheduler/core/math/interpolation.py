"""Linear interpolation / extrapolation over (x, y) lookup tables."""

Point = tuple[float, float]
Points = list[Point]


def _lerp(low: Point, high: Point, x: float) -> float:
    """Value on the line through ``low`` and ``high`` at ``x`` (also extrapolates)."""
    x0, y0 = low
    x1, y1 = high
    frac = (x - x0) / (x1 - x0)
    return y0 + frac * (y1 - y0)


def interpolate(points: Points, x: float) -> float:
    """Linear interpolation of y at x, clamped to the endpoints (points sorted by x)."""
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for idx in range(len(points) - 1):
        low, high = points[idx], points[idx + 1]
        if low[0] <= x <= high[0]:
            return _lerp(low, high, x)
    return points[-1][1]


def extrapolate_linear(points: Points, x: float) -> float:
    """Linear extrapolation from the last two points (for x beyond the table)."""
    return _lerp(points[-2], points[-1], x)
