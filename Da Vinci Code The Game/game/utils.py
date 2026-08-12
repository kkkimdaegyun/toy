from __future__ import annotations

import socket


def sort_tiles(tiles):
    """Sort low to high, with black before white for equal values."""
    return sorted(tiles, key=lambda tile: (tile.value, 0 if tile.color == "black" else 1, tile.id))


def preferred_lan_ip() -> str | None:
    """Find the outbound LAN IPv4 without sending a network packet."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        address = probe.getsockname()[0]
        return address if address and not address.startswith("127.") else None
    except OSError:
        return None
    finally:
        probe.close()

