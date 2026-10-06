"""Colours of the measurements, shared by the viewer and the report (no GUI dependencies)."""

PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2",
           "#17becf", "#bcbd22", "#7f7f7f"]


def style_of(index: int):
    """Colour per measurement; from the 11th on the same colours are used with dashed lines."""
    return PALETTE[index % len(PALETTE)], (index // len(PALETTE)) % 2 == 1
