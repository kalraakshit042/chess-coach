"""
Opening resource database.
Maps ECO codes/prefixes to curated study resources.
"""
from models import Resource

# Lichess opening explorer base URL — always valid for any opening
LICHESS_OPENING_BASE = "https://lichess.org/opening"

# YouTube channel links (channel level, not specific videos)
YOUTUBE_NARODITSKY = "https://www.youtube.com/@DanielNaroditsky"
YOUTUBE_GOTHAM = "https://www.youtube.com/@GothamChess"
YOUTUBE_JOHN_BARTHOLOMEW = "https://www.youtube.com/@JohnBartholomew"

# ECO prefix → resources mapping
# Keys: exact ECO (e.g. "B23") or prefix (e.g. "B2") or letter (e.g. "B")
_RESOURCE_DB: dict[str, list[dict]] = {
    # ── E-pawn openings (1.e4 e5) ──────────────────────────────────────
    "C20": [  # King's Pawn Game
        {"title": "Open Games on Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/King%27s_Pawn_Game", "resource_type": "lichess"},
    ],
    "C60": [  # Ruy Lopez
        {"title": "Ruy Lopez — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Ruy_Lopez", "resource_type": "lichess"},
        {"title": "Ruy Lopez Deep Dive — Daniel Naroditsky", "url": YOUTUBE_NARODITSKY, "resource_type": "youtube"},
    ],
    "C50": [  # Italian Game
        {"title": "Italian Game — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Italian_Game", "resource_type": "lichess"},
        {"title": "Italian Game Guide — GothamChess", "url": YOUTUBE_GOTHAM, "resource_type": "youtube"},
    ],
    "C44": [  # Scotch Game / King's Gambit area
        {"title": "Scotch Game — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Scotch_Game", "resource_type": "lichess"},
    ],
    "C30": [  # King's Gambit
        {"title": "King's Gambit — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/King%27s_Gambit", "resource_type": "lichess"},
    ],
    "C40": [  # Petroff / Latvian
        {"title": "Petrov Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Petrov%27s_Defense", "resource_type": "lichess"},
    ],
    "C00": [  # French Defense
        {"title": "French Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/French_Defense", "resource_type": "lichess"},
        {"title": "French Defense Guide — GothamChess", "url": YOUTUBE_GOTHAM, "resource_type": "youtube"},
    ],
    "C10": [  # French Defense variants
        {"title": "French Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/French_Defense", "resource_type": "lichess"},
    ],
    # ── Sicilian ───────────────────────────────────────────────────────
    "B20": [
        {"title": "Sicilian Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Sicilian_Defense", "resource_type": "lichess"},
        {"title": "Sicilian Defense Speedrun — Daniel Naroditsky", "url": YOUTUBE_NARODITSKY, "resource_type": "youtube"},
    ],
    "B30": [
        {"title": "Sicilian Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Sicilian_Defense", "resource_type": "lichess"},
        {"title": "Sicilian Guide — GothamChess", "url": YOUTUBE_GOTHAM, "resource_type": "youtube"},
    ],
    "B40": [
        {"title": "Sicilian Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Sicilian_Defense", "resource_type": "lichess"},
    ],
    "B50": [
        {"title": "Sicilian Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Sicilian_Defense", "resource_type": "lichess"},
    ],
    "B60": [  # Sicilian Najdorf
        {"title": "Sicilian Najdorf — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Sicilian_Defense_Najdorf_Variation", "resource_type": "lichess"},
        {"title": "Najdorf Deep Dive — Daniel Naroditsky", "url": YOUTUBE_NARODITSKY, "resource_type": "youtube"},
    ],
    "B70": [  # Sicilian Dragon
        {"title": "Sicilian Dragon — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Sicilian_Defense_Dragon_Variation", "resource_type": "lichess"},
        {"title": "Sicilian Dragon Guide — GothamChess", "url": YOUTUBE_GOTHAM, "resource_type": "youtube"},
    ],
    "B80": [  # Sicilian Scheveningen
        {"title": "Sicilian Scheveningen — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Sicilian_Defense_Scheveningen_Variation", "resource_type": "lichess"},
    ],
    # ── Caro-Kann ──────────────────────────────────────────────────────
    "B10": [
        {"title": "Caro-Kann Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Caro-Kann_Defense", "resource_type": "lichess"},
        {"title": "Caro-Kann Fundamentals — John Bartholomew", "url": YOUTUBE_JOHN_BARTHOLOMEW, "resource_type": "youtube"},
    ],
    # ── Pirc / Modern ──────────────────────────────────────────────────
    "B06": [
        {"title": "Modern Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Modern_Defense", "resource_type": "lichess"},
    ],
    "B07": [
        {"title": "Pirc Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Pirc_Defense", "resource_type": "lichess"},
    ],
    # ── Queen's Gambit / d4 openings ───────────────────────────────────
    "D00": [
        {"title": "Queen's Pawn Game — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Queen%27s_Pawn_Game", "resource_type": "lichess"},
    ],
    "D20": [  # Queen's Gambit Accepted
        {"title": "Queen's Gambit Accepted — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Queen%27s_Gambit_Accepted", "resource_type": "lichess"},
    ],
    "D30": [  # Queen's Gambit Declined
        {"title": "Queen's Gambit Declined — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Queen%27s_Gambit_Declined", "resource_type": "lichess"},
        {"title": "QGD Guide — GothamChess", "url": YOUTUBE_GOTHAM, "resource_type": "youtube"},
    ],
    "D40": [
        {"title": "Queen's Gambit Declined — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Queen%27s_Gambit_Declined", "resource_type": "lichess"},
    ],
    "D50": [  # QGD with 5.Bg5
        {"title": "Queen's Gambit Declined — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Queen%27s_Gambit_Declined", "resource_type": "lichess"},
    ],
    # ── Indian Defenses ────────────────────────────────────────────────
    "E00": [
        {"title": "Catalan Opening — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Catalan_Opening", "resource_type": "lichess"},
    ],
    "E20": [  # Nimzo-Indian
        {"title": "Nimzo-Indian Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/Nimzo-Indian_Defense", "resource_type": "lichess"},
        {"title": "Nimzo-Indian Guide — Daniel Naroditsky", "url": YOUTUBE_NARODITSKY, "resource_type": "youtube"},
    ],
    "E60": [  # King's Indian
        {"title": "King's Indian Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/King%27s_Indian_Defense", "resource_type": "lichess"},
        {"title": "King's Indian Guide — GothamChess", "url": YOUTUBE_GOTHAM, "resource_type": "youtube"},
    ],
    "E80": [
        {"title": "King's Indian Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/King%27s_Indian_Defense", "resource_type": "lichess"},
    ],
    "E90": [
        {"title": "King's Indian Defense — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/King%27s_Indian_Defense", "resource_type": "lichess"},
    ],
    # ── English / Flank openings ───────────────────────────────────────
    "A10": [
        {"title": "English Opening — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/English_Opening", "resource_type": "lichess"},
    ],
    "A20": [
        {"title": "English Opening — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/English_Opening", "resource_type": "lichess"},
    ],
    "A30": [
        {"title": "English Opening — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/English_Opening", "resource_type": "lichess"},
    ],
    # ── London System ──────────────────────────────────────────────────
    "D02": [
        {"title": "London System — Lichess Opening Explorer", "url": f"{LICHESS_OPENING_BASE}/London_System", "resource_type": "lichess"},
        {"title": "London System Guide — GothamChess", "url": YOUTUBE_GOTHAM, "resource_type": "youtube"},
    ],
}

# Generic fallback resources by ECO letter
_LETTER_FALLBACK: dict[str, list[dict]] = {
    "A": [{"title": "Flank Openings on Lichess", "url": f"{LICHESS_OPENING_BASE}", "resource_type": "lichess"}],
    "B": [{"title": "Semi-Open Games on Lichess", "url": f"{LICHESS_OPENING_BASE}/Sicilian_Defense", "resource_type": "lichess"}],
    "C": [{"title": "Open Games on Lichess", "url": f"{LICHESS_OPENING_BASE}/King%27s_Pawn_Game", "resource_type": "lichess"}],
    "D": [{"title": "Closed Games on Lichess", "url": f"{LICHESS_OPENING_BASE}/Queen%27s_Gambit", "resource_type": "lichess"}],
    "E": [{"title": "Indian Defenses on Lichess", "url": f"{LICHESS_OPENING_BASE}/Indian_Defense", "resource_type": "lichess"}],
}


def get_resources_for_opening(eco: str, opening_name: str) -> list[Resource]:
    """
    Return curated resources for a given ECO code.
    Looks up exact ECO first, then 3-char prefix, then letter fallback.
    Always includes the Lichess opening explorer link.
    """
    if not eco or eco == "?":
        return []

    eco = eco.upper().strip()
    resources_raw: list[dict] = []

    # Try exact match first, then 3-char prefix, then letter
    for key in [eco, eco[:3], eco[:2], eco[:1]]:
        if key in _RESOURCE_DB:
            resources_raw = _RESOURCE_DB[key]
            break

    # Fall back to letter-level
    if not resources_raw and eco[0] in _LETTER_FALLBACK:
        resources_raw = _LETTER_FALLBACK[eco[0]]

    # Always add a Lichess opening explorer link using the opening name
    lichess_name = opening_name.replace(" ", "_").replace("'", "%27").replace(",", "")
    lichess_url = f"{LICHESS_OPENING_BASE}/{lichess_name}"

    has_lichess = any(r.get("resource_type") == "lichess" for r in resources_raw)
    if not has_lichess:
        resources_raw = [
            {"title": f"{opening_name} on Lichess Opening Explorer", "url": lichess_url, "resource_type": "lichess"}
        ] + resources_raw

    return [Resource(**r) for r in resources_raw[:3]]  # max 3 resources
