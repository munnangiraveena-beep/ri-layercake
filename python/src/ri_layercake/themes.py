"""Built-in palettes. Each maps theme slots to colours, so the web canvas and
SVG can draw theme references, and PPTX ships them as real theme XML."""

from __future__ import annotations

PALETTES: dict[str, dict[str, str]] = {
    "ocean": {
        "dk1": "1B2733", "lt1": "FFFFFF", "dk2": "16324F", "lt2": "E8EEF3",
        "accent1": "0E5A8A", "accent2": "1C7C9C", "accent3": "3FA7B5",
        "accent4": "7BC4C4", "accent5": "E0A33B", "accent6": "C4513A",
        "hlink": "0E5A8A", "folHlink": "5B4B8A",
    },
    "slate": {
        "dk1": "1F2328", "lt1": "FFFFFF", "dk2": "2E3A46", "lt2": "EDEFF2",
        "accent1": "3D4C5C", "accent2": "5A6B7D", "accent3": "7D8FA3",
        "accent4": "A7B5C4", "accent5": "C9A227", "accent6": "B4443A",
        "hlink": "3D4C5C", "folHlink": "6B5B7B",
    },
    "ember": {
        "dk1": "2A1F1A", "lt1": "FFFFFF", "dk2": "4A2A1E", "lt2": "F6EEE8",
        "accent1": "9C3D1C", "accent2": "C2562A", "accent3": "D9834B",
        "accent4": "E8B27D", "accent5": "4F7C8A", "accent6": "7A2E4A",
        "hlink": "9C3D1C", "folHlink": "6B4B3A",
    },
}

SLOT_ALIASES = {"tx1": "dk1", "bg1": "lt1", "tx2": "dk2", "bg2": "lt2"}
FONTS = {"major": "Calibri", "minor": "Calibri"}
WARN_HEX = "C0392B"


def resolve(palette: str, theme: str, tint: float = 0.0) -> str:
    """Hex colour (no #) for a theme slot with a tint toward white."""
    pal = PALETTES.get(palette, PALETTES["ocean"])
    hexv = pal[SLOT_ALIASES.get(theme, theme)]
    if not tint:
        return hexv
    rgb = [int(hexv[i:i + 2], 16) for i in (0, 2, 4)]
    mixed = [round(c + (255 - c) * tint) for c in rgb]
    return "".join(f"{c:02X}" for c in mixed)
