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
# Olivereta eliminada: no está incluida en ninguno de los 3 modelos multi-estación.
STATIONS: dict[str, tuple[float, float]] = {
    "Port Moll Trans. Ponent":  (39.45926486, -0.32321741),
    "Pista de Silla":           (39.45806013, -0.37665323),
    "Vivers":                   (39.47948825, -0.36955032),
    "Politècnic":               (39.47962193, -0.33740740),
    "Av. França":               (39.45750439, -0.34268990),
    "Molí del Sol":             (39.48113875, -0.40855865),
    "Bulevard Sud":             (39.45037852, -0.39631399),
    "Centre":                   (39.47071883, -0.37648469),
    "Port llit antic Túria":    (39.45051894, -0.32894501),
}

STATION_NAMES: list[str] = list(STATIONS.keys())

# Códigos públicos RVVCCA usados como `paramidStation` en el endpoint Pentaho JSON.
STATION_CODES: dict[str, str] = {
    "Port Moll Trans. Ponent":  "46250301",
    "Pista de Silla":           "46250030",
    "Vivers":                   "46250043",
    "Politècnic":               "46250046",
    "Av. França":               "46250047",
    "Molí del Sol":             "46250048",
    "Bulevard Sud":             "46250050",
    "Centre":                   "46250054",
    "Port llit antic Túria":    "46250302",
}

# Los modelos multi-estación se entrenaron con un dataset histórico que usa nombres
# distintos a los actuales (traducción al castellano, sin acentos catalanes).
# Este diccionario mapea los nombres del modelo → nombres canónicos (los que usamos
# nosotros). "Puerto Valencia" no aparece porque no corresponde a ninguna centralita
# activa de la RVVCCA actual y se ignora al construir las predicciones.
MODEL_NAME_TO_CANONICAL: dict[str, str] = {
    "Avda. Francia":             "Av. França",
    "Molí del Sol":              "Molí del Sol",
    "Pista Silla":               "Pista de Silla",
    "Politécnico":               "Politècnic",
    "Valencia Centro":           "Centre",
    "Puerto Moll Trans. Ponent": "Port Moll Trans. Ponent",
    "Puerto llit antic Túria":   "Port llit antic Túria",
    "Bulevard Sud":              "Bulevard Sud",
    "Viveros":                   "Vivers",
}

CANONICAL_TO_MODEL_NAME: dict[str, str] = {v: k for k, v in MODEL_NAME_TO_CANONICAL.items()}

# Cobertura física real según las mediciones publicadas por la RVVCCA:
# qué centralitas tienen efectivamente sensor para cada contaminante.
# El CSV de previsiones puede traer valores para estaciones sin sensor real
# (extrapolaciones); aquí filtramos para no mostrarlas como dato fiable.
#   - Vivers / Bulevard Sud NO tienen sensor de PM2.5
#   - Centre NO tiene sensor de O3
#   - Todas miden NO2
PHYSICAL_COVERAGE: dict[str, list[str]] = {
    "PM25": [
        "Port Moll Trans. Ponent", "Pista de Silla", "Politècnic",
        "Av. França", "Molí del Sol", "Centre", "Port llit antic Túria",
    ],
    "NO2": STATION_NAMES,
    "O3": [
        "Port Moll Trans. Ponent", "Pista de Silla", "Vivers", "Politècnic",
        "Av. França", "Molí del Sol", "Bulevard Sud", "Port llit antic Túria",
    ],
}
