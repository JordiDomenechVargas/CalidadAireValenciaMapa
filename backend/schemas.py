"""Pydantic schemas — contrato HTTP del backend."""
from datetime import datetime
from pydantic import BaseModel, Field


class Station(BaseModel):
    name: str
    lat: float
    lon: float


class Meteo(BaseModel):
    Temperatura: float
    Humedad_relativa: float
    Presion: float
    Velocidad_viento: float
    Direccion_viento: float
    Precipitacion: float


class AirReading(BaseModel):
    """Última lectura real publicada por la GVA para esa estación. Cada gas es
    `None` si la centralita no tiene sensor para ese contaminante (p. ej. Centre
    no mide O3, Vivers no mide PM2.5)."""
    O3: float | None = None
    NO2: float | None = None
    PM25: float | None = None


class Snapshot(BaseModel):
    """Estado completo de la red.

    `forecasts[pollutant][station]` = lista de 169 valores horarios (idx 0 = now,
    idx 168 = now + 168 h = +7 días). Si una estación no es soportada por un modelo
    concreto NO aparece en su dict.

    `supported_stations[pollutant]` = lista canónica de estaciones que cada modelo
    puede predecir (útil para que el frontend sepa cuáles colorear vs. cuáles dejar
    en gris).
    """
    generated_at: datetime
    last_real_data_at: datetime
    stations: list[Station]
    meteo: Meteo
    current: dict[str, AirReading]
    forecasts: dict[str, dict[str, list[float]]]
    supported_stations: dict[str, list[str]]


class HealthResponse(BaseModel):
    status: str = "ok"
    last_snapshot: datetime | None = None
    last_real_data_at: datetime | None = None
    next_refresh_in_min: int = Field(default=0, description="Minutos hasta el próximo refresco programado")
    pollutants: list[str] = Field(default_factory=list)
