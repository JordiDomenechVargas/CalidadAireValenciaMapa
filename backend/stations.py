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

# Códigos públicos RVVCCA usados como `paramidStation` en el endpoint Pentaho JSON.
# Fuente: https://rvvcca.pica.gva.es/es/ultimos-datos
STATION_CODES: dict[str, str] = {
    "Port Moll Trans. Ponent":  "46250301",
    "Pista de Silla":           "46250030",
    "Vivers":                   "46250043",
    "Politècnic":               "46250046",
    "Av. França":               "46250047",
    "Molí del Sol":             "46250048",
    "Bulevard Sud":             "46250050",
    "Centre":                   "46250054",
    "Olivereta":                "46250055",
    "Port llit antic Túria":    "46250302",
}
