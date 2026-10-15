"""Read SVG path data (the 'd' attribute) and flatten its curves into straight segments.

Supported commands, in both absolute (upper case) and relative (lower case) forms:
M (move), L (line), H and V (horizontal and vertical lines), C (cubic curve), S (smooth cubic),
Q (quadratic curve), T (smooth quadratic), A (elliptical arc), and Z (close the subpath).
Arc flags must be separate numbers, written as 0 or 1 with spaces around them.
"""

import math
import re

from ai_paint.errors import PaintError

COORD_LIMIT = 100_000
MAX_FLAT_POINTS = 20_000
TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
ARGUMENTS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def _tokens(data: str) -> list[str]:
    tokens = TOKEN.findall(data)
    leftover = TOKEN.sub("", data).replace(",", " ").split()
    if leftover:
        raise PaintError(f"path data has text it does not understand: {leftover[0]!r}")
    return tokens


def _steps(*points) -> int:
    """How many straight pieces a curve needs so it looks smooth: roughly one per two pixels."""
    length = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
    return max(8, min(400, int(length / 2)))


def _cubic(p0, c1, c2, p1) -> list:
    steps = _steps(p0, c1, c2, p1)
    out = []
    for step in range(1, steps + 1):
        t = step / steps
        u = 1 - t
        out.append((
            u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p1[0],
            u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p1[1],
        ))
    return out


def _quadratic(p0, c, p1) -> list:
    steps = _steps(p0, c, p1)
    out = []
    for step in range(1, steps + 1):
        t = step / steps
        u = 1 - t
        out.append((
            u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
            u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1],
        ))
    return out


def _angle(ux, uy, vx, vy) -> float:
    sign = 1 if ux * vy - uy * vx >= 0 else -1
    dot = (ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy))
    return sign * math.acos(max(-1.0, min(1.0, dot)))


def _arc(start, rx, ry, rotation_deg, large, sweep, end) -> list:
    """Flatten an SVG elliptical arc (endpoint form, converted to centre form as in the SVG specification)."""
    x1, y1 = start
    x2, y2 = end
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [end]
    phi = math.radians(rotation_deg)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    lam = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if lam > 1:
        rx *= math.sqrt(lam)
        ry *= math.sqrt(lam)
    numerator = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    denominator = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coefficient = math.sqrt(max(0.0, numerator / denominator)) if denominator else 0.0
    if large == sweep:
        coefficient = -coefficient
    cxp = coefficient * rx * y1p / ry
    cyp = -coefficient * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2
    ux, uy = (x1p - cxp) / rx, (y1p - cyp) / ry
    vx, vy = (-x1p - cxp) / rx, (-y1p - cyp) / ry
    theta1 = _angle(1.0, 0.0, ux, uy)
    delta = _angle(ux, uy, vx, vy)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    if sweep and delta < 0:
        delta += 2 * math.pi
    steps = max(16, min(400, int(abs(delta) * max(rx, ry))))
    out = []
    for step in range(1, steps + 1):
        theta = theta1 + delta * step / steps
        out.append((
            cx + rx * math.cos(theta) * cos_phi - ry * math.sin(theta) * sin_phi,
            cy + rx * math.cos(theta) * sin_phi + ry * math.sin(theta) * cos_phi,
        ))
    out[-1] = end
    return out


def parse(data: str) -> list[tuple[list, bool]]:
    """Return the subpaths as (points, closed) pairs, with every curve flattened to points."""
    if not isinstance(data, str) or not data.strip():
        raise PaintError("path data must be SVG path text such as 'M 0 0 L 10 0 L 10 10 Z'")
    tokens = _tokens(data)
    if not tokens or tokens[0] not in ("M", "m"):
        raise PaintError("path data must start with a move command, M or m")

    subpaths: list[tuple[list, bool]] = []
    points: list = []
    closed = False
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    last_cubic = None  # the second control point of the last cubic curve, for S
    last_quad = None  # the control point of the last quadratic curve, for T
    command = None
    index = 0

    def finish():
        nonlocal points, closed
        if len(points) >= 2:
            subpaths.append((points, closed))
        points, closed = [], False

    def check_limit():
        total = sum(len(p) for p, _ in subpaths) + len(points)
        if total > MAX_FLAT_POINTS:
            raise PaintError(f"path has more than {MAX_FLAT_POINTS} points after curves are flattened")

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
            if command in "Zz":
                if points:
                    closed = True
                    finish()
                current = start
                last_cubic = last_quad = None
                continue
        elif command is None or command in "Zz":
            raise PaintError("path data has numbers with no command in front of them")
        letter = command.upper()
        count = ARGUMENTS[letter]
        numbers = tokens[index:index + count]
        if len(numbers) < count or any(not re.match(r"^[-+.\d]", t) for t in numbers):
            raise PaintError(f"path command {command} needs {count} numbers")
        values = [float(t) for t in numbers]
        index += count
        relative = command.islower()
        base_x, base_y = current if relative else (0.0, 0.0)

        def absolute(x, y):
            point = (base_x + x, base_y + y)
            if max(abs(point[0]), abs(point[1])) > COORD_LIMIT:
                raise PaintError(f"path coordinates must be between -{COORD_LIMIT} and {COORD_LIMIT}")
            return point

        if letter == "M":
            finish()
            current = start = absolute(values[0], values[1])
            points = [current]
            # Further coordinate pairs after M are line-tos.
            command = "l" if relative else "L"
            last_cubic = last_quad = None
        elif letter == "L":
            if not points:
                points = [current]
            current = absolute(values[0], values[1])
            points.append(current)
            last_cubic = last_quad = None
        elif letter == "H":
            if not points:
                points = [current]
            x = (current[0] + values[0]) if relative else values[0]
            current = (x, current[1])
            points.append(current)
            last_cubic = last_quad = None
        elif letter == "V":
            if not points:
                points = [current]
            y = (current[1] + values[0]) if relative else values[0]
            current = (current[0], y)
            points.append(current)
            last_cubic = last_quad = None
        elif letter in "CS":
            if not points:
                points = [current]
            if letter == "C":
                c1 = absolute(values[0], values[1])
                c2 = absolute(values[2], values[3])
                end = absolute(values[4], values[5])
            else:
                c1 = (2 * current[0] - last_cubic[0], 2 * current[1] - last_cubic[1]) if last_cubic else current
                c2 = absolute(values[0], values[1])
                end = absolute(values[2], values[3])
            points.extend(_cubic(current, c1, c2, end))
            last_cubic = c2
            last_quad = None
            current = end
        elif letter == "A":
            if not points:
                points = [current]
            rx, ry, rotation, large, sweep = values[0], values[1], values[2], values[3], values[4]
            if large not in (0.0, 1.0) or sweep not in (0.0, 1.0):
                raise PaintError("arc flags must be 0 or 1")
            end = absolute(values[5], values[6])
            points.extend(_arc(current, rx, ry, rotation, int(large), int(sweep), end))
            current = end
            last_cubic = last_quad = None
        elif letter in "QT":
            if not points:
                points = [current]
            if letter == "Q":
                control = absolute(values[0], values[1])
                end = absolute(values[2], values[3])
            else:
                control = (2 * current[0] - last_quad[0], 2 * current[1] - last_quad[1]) if last_quad else current
                end = absolute(values[0], values[1])
            points.extend(_quadratic(current, control, end))
            last_quad = control
            last_cubic = None
            current = end
        check_limit()

    finish()
    if not subpaths:
        raise PaintError("path data has no line or curve to draw; it needs at least two points")
    return subpaths


def spline(points: list, closed: bool = False) -> list:
    """Smooth curve through the points (Catmull-Rom), flattened to straight pieces.

    The curve passes through every point. With `closed`, it loops back to the first point.
    """
    count = len(points)
    if count < 2:
        raise PaintError("a smooth curve needs at least two points")

    def at(index):
        if closed:
            return points[index % count]
        return points[max(0, min(count - 1, index))]

    out = [(float(points[0][0]), float(points[0][1]))]
    segments = count if closed else count - 1
    for i in range(segments):
        p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.extend(_cubic(p1, c1, c2, p2))
    return out

