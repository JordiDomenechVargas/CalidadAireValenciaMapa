"""Cliente HTTP del backend de predicciones. Cacheado en Streamlit."""
import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _get_setting(key: str, default: str = "") -> str:
    """Lee config primero de `st.secrets` (Streamlit Cloud), luego de variables de
    entorno (.env local), y por último el default. Streamlit Cloud no siempre expone
    los secrets como env vars, así que hay que consultarlos explícitamente."""
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except (FileNotFoundError, Exception):
        pass
    return os.getenv(key, default)


API_URL = _get_setting("API_URL", "http://localhost:8000").rstrip("/")
REFRESH_TOKEN = _get_setting("REFRESH_TOKEN", "")


class BackendUnavailable(RuntimeError):
    """No se pudo contactar con el backend de predicciones."""


@st.cache_data(ttl=300, show_spinner=False)
def get_snapshot() -> dict:
    """GET /snapshot · devuelve un dict con stations, meteo, forecasts y current."""
    try:
        r = requests.get(f"{API_URL}/snapshot", timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise BackendUnavailable(str(e)) from e


def force_refresh() -> dict:
    """POST /refresh · regenera el snapshot en el backend y vacía la cache local."""
    headers = {"X-Refresh-Token": REFRESH_TOKEN} if REFRESH_TOKEN else {}
    try:
        r = requests.post(f"{API_URL}/refresh", headers=headers, timeout=120)
        r.raise_for_status()
    except requests.RequestException as e:
        raise BackendUnavailable(str(e)) from e
    st.cache_data.clear()
    return r.json()


def health() -> dict:
    """GET /health · estado del backend (timestamp del snapshot, próximo refresco)."""
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise BackendUnavailable(str(e)) from e
