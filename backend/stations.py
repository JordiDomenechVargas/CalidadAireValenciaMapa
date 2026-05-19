"""Catálogo de centralitas RVVCCA en Valencia + helpers para emparejamiento de nombres."""
import unicodedata


def normalize(s: str) -> str:
    """Quita acentos/diacríticos y pasa a minúsculas para emparejar nombres robustamente."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower()


# Coordenadas y nombres oficiales RVVCCA (Generalitat Valenciana):
# https://rvvcca.pica.gva.es/es/ultimos-datos
STATIONS: dict[str, tuple[float, float]] = {
    "Port Moll Trans. Ponent":  (39.45926486, -0.32321741),
    "Pista de Silla":           (39.45806013, -0.37665323),
    "Vivers":                   (39.47948825, -0.36955032),
    "Politècnic":               (39.47962193, -0.33740740),
    "Av. França":               (39.45750439, -0.34268990),
    "Molí del Sol":             (39.48113875, -0.40855865),
    "Bulevard Sud":             (39.45037852, -0.39631399),
    "Centre":                   (39.47071883, -0.37648469),
    "Olivereta":                (39.46923859, -0.40603766),
    "Port llit antic Túria":    (39.45051894, -0.32894501),
}

STATION_NAMES: list[str] = list(STATIONS.keys())

# Substring distintivo (normalizado, sin acentos) que debe aparecer en la fila de la
# tabla scrapeada para emparejar con cada estación. Evita colisiones entre estaciones
# que empiezan por la misma palabra (ej. "Port Moll" vs "Port llit").
STATION_MATCH_KEYS: dict[str, str] = {
    "Port Moll Trans. Ponent":  "port moll",
    "Pista de Silla":           "pista",
    "Vivers":                   "vivers",
    "Politècnic":               "politecnic",
    "Av. França":               "franca",
    "Molí del Sol":             "moli",
    "Bulevard Sud":             "bulevard",
    "Centre":                   "centre",
    "Olivereta":                "olivereta",
    "Port llit antic Túria":    "turia",
}


def match_station(raw_name: str) -> str | None:
    """Dado el nombre tal como aparece en la tabla scrapeada, devuelve la clave canónica
    de STATIONS o None si no encaja con ninguna."""
    raw_norm = normalize(raw_name)
    for name, key in STATION_MATCH_KEYS.items():
        if key in raw_norm:
            return name
    return None
