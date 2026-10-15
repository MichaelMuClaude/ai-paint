"""Gradient fills: a colour that changes across a shape, linearly or radially.

A gradient is built from stops, each a position from 0 to 1 and an RGBA colour. Positions outside the
gradient's own span take the colour of the nearest stop.
"""

import numpy as np


class Gradient:
    def __init__(self, kind: str, stops: list, **geometry):
        """`stops` is a list of (position, (r, g, b, a)) sorted by position."""
        self.kind = kind
        self.positions = np.array([position for position, _ in stops], dtype=np.float64)
        self.colours = np.array([colour for _, colour in stops], dtype=np.float64)
        self.geometry = geometry

    def _t(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Where each pixel centre falls along the gradient: 0 at the start, 1 at the end."""
        if self.kind == "linear":
            (fx, fy), (tx, ty) = self.geometry["start"], self.geometry["end"]
            dx, dy = tx - fx, ty - fy
            t = ((x - fx) * dx + (y - fy) * dy) / (dx * dx + dy * dy)
        else:
            cx, cy = self.geometry["centre"]
            t = np.hypot(x - cx, y - cy) / self.geometry["radius"]
        return np.clip(t, 0.0, 1.0)

    def render(self, region: tuple[int, int, int, int]) -> np.ndarray:
        """The RGBA colour (0 to 255) of every pixel in `region` (x0, y0, x1, y1), as an array."""
        x0, y0, x1, y1 = region
        xs = np.arange(x0, x1, dtype=np.float64) + 0.5
        ys = np.arange(y0, y1, dtype=np.float64) + 0.5
        x, y = np.meshgrid(xs, ys)
        t = self._t(x, y)
        out = np.empty((y1 - y0, x1 - x0, 4), dtype=np.float64)
        for channel in range(4):
            out[..., channel] = np.interp(t, self.positions, self.colours[:, channel])
        return np.clip(np.round(out), 0, 255).astype(np.uint8)
