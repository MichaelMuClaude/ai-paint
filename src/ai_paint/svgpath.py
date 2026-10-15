"""Read SVG path data (the 'd' attribute) and flatten its curves into straight segments.

Supported commands, in both absolute (upper case) and relative (lower case) forms:
M (move), L (line), H and V (horizontal and vertical lines), C (cubic curve), S (smooth cubic),
Q (quadratic curve), T (smooth quadratic), and Z (close the subpath).
Arcs (A) are not supported; approximate them with curves.
"""

import math
import re

from ai_paint.errors import PaintError

COORD_LIMIT = 100_000
MAX_FLAT_POINTS = 20_000
TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
ARGUMENTS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "Z": 0}


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
