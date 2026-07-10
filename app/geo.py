"""Canonical geo-spatial ids for Nigerian states.

The id is GADM-derived (see data/svg/nigeria-lga.geojson, ID_2 = "NGA.<state>.<lga>_1"),
lowercased with dots removed and levels underscore-separated:

    state  -> "nga_<state>"          e.g. Akwa Ibom -> "nga_3"
    lga    -> "nga_<state>_<lga>"    (levels kept separate so ids never collide)

Always key states by this id in the DB, API paths and frontend requests — never by
name. Names vary across this repo's data (Nasarawa/Nassarawa, FCT/Federal Capital
Territory, Cross River/Cross Rivers) which is exactly why name lookups are fragile.
"""

# GADM state index (1..37) -> the state's canonical name as stored in our `states`
# table. Order/index come straight from the geojson.
_STATE_BY_NUM: dict[int, str] = {
    1: "Abia", 2: "Adamawa", 3: "Akwa Ibom", 4: "Anambra", 5: "Bauchi", 6: "Bayelsa",
    7: "Benue", 8: "Borno", 9: "Cross River", 10: "Delta", 11: "Ebonyi", 12: "Edo",
    13: "Ekiti", 14: "Enugu", 15: "FCT", 16: "Gombe", 17: "Imo", 18: "Jigawa",
    19: "Kaduna", 20: "Kano", 21: "Katsina", 22: "Kebbi", 23: "Kogi", 24: "Kwara",
    25: "Lagos", 26: "Nasarawa", 27: "Niger", 28: "Ogun", 29: "Ondo", 30: "Osun",
    31: "Oyo", 32: "Plateau", 33: "Rivers", 34: "Sokoto", 35: "Taraba", 36: "Yobe",
    37: "Zamfara",
}

# The whole-country pseudo-state, used by national records (e.g. presidential runs
# stored with state == "Nigeria").
NATIONAL_GEO_ID = "nga"

# geo_id -> canonical state name.
GEO_TO_NAME: dict[str, str] = {f"nga_{n}": name for n, name in _STATE_BY_NUM.items()}
GEO_TO_NAME[NATIONAL_GEO_ID] = "Nigeria"


def _norm(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


# normalized name (incl. known variants) -> geo_id.
_NAME_TO_GEO: dict[str, str] = {_norm(name): gid for gid, name in GEO_TO_NAME.items()}
_NAME_TO_GEO.update({
    _norm("Nassarawa"): "nga_26",
    _norm("Federal Capital Territory"): "nga_15",
    _norm("Abuja"): "nga_15",
    _norm("Cross Rivers"): "nga_9",
})


def state_geo_id(name: str) -> str | None:
    """geo_id for a state name (tolerant of the spelling variants in our data), or
    None if the name isn't a recognised state/national record."""
    return _NAME_TO_GEO.get(_norm(name))


def state_name(geo_id: str) -> str | None:
    """Canonical state name for a geo_id, or None if unknown."""
    return GEO_TO_NAME.get(geo_id)


def lga_geo_id(state_geo: str, lga_index: int) -> str:
    """geo_id for an LGA given its state geo_id and 1-based GADM LGA index."""
    return f"{state_geo}_{lga_index}"
