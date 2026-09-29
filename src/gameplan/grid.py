from __future__ import annotations


def grid_shape(x_range, z_range, cell_in: float) -> tuple[int, int]:
    step = cell_in / 12.0
    return round((x_range[1] - x_range[0]) / step), round((z_range[1] - z_range[0]) / step)
