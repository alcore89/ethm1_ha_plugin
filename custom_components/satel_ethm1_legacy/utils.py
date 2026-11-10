"""Small helpers for SATEL ETHM-1 Legacy."""

from __future__ import annotations


def parse_zone_spec(value: str) -> set[int]:
    """Parse a zone list such as '1-8,10,12' into a set of zone numbers."""
    value = (value or "").strip()
    if not value:
        return set()

    zones: set[int] = set()
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue

        if "-" in chunk:
            parts = chunk.split("-", 1)
            if len(parts) != 2:
                raise ValueError("invalid_zone_spec")
            start = int(parts[0].strip())
            end = int(parts[1].strip())
            if start > end:
                raise ValueError("invalid_zone_spec")
            for zone in range(start, end + 1):
                if not 1 <= zone <= 256:
                    raise ValueError("invalid_zone_spec")
                zones.add(zone)
        else:
            zone = int(chunk)
            if not 1 <= zone <= 256:
                raise ValueError("invalid_zone_spec")
            zones.add(zone)

    return zones
