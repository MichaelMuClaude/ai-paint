"""Screentones: the dot patterns that manga artists stick on paper to show grey.

A screentone is a grid of dots, rotated to an angle. Each dot covers a share of its cell equal to the
density, so density 0.3 shows as 30 per cent grey, and the dots are anti-aliased.
"""

import math

import numpy as np


class ScreenTone:
    def __init__(self, density: float, cell: float, angle: float, colour: tuple):
        """`cell` is the distance between dot centres in pixels; `angle` is in degrees."""
        self.density = density
        self.cell = cell
        self.angle = math.radians(angle)
        self.colour = colour

    def render(self, region: tuple[int, int, int, int]) -> np.ndarray:
        """The RGBA colour of every pixel in `region` (x0, y0, x1, y1), with the dot coverage as alpha."""
        x0, y0, x1, y1 = region
        xs = np.arange(x0, x1, dtype=np.float64) + 0.5
        ys = np.arange(y0, y1, dtype=np.float64) + 0.5
        x, y = np.meshgrid(xs, ys)
        cos_a, sin_a = math.cos(self.angle), math.sin(self.angle)
        u = (x * cos_a + y * sin_a) / self.cell
        v = (-x * sin_a + y * cos_a) / self.cell
        # distance from the nearest dot centre, measured in cells
        du = u - np.floor(u) - 0.5
        dv = v - np.floor(v) - 0.5
        distance = np.hypot(du, dv) * self.cell
        # a dot of radius R covers a share of the cell equal to the density: pi R^2 = density * cell^2
        radius = self.cell * math.sqrt(self.density / math.pi)
        coverage = np.clip(radius - distance + 0.5, 0.0, 1.0)
        out = np.empty((y1 - y0, x1 - x0, 4), dtype=np.uint8)
        out[..., :3] = self.colour[:3]
        out[..., 3] = np.round(coverage * self.colour[3]).astype(np.uint8)
        return out
