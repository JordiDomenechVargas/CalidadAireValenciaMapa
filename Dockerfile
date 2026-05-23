# Dockerfile preparado para desplegar el backend en Hugging Face Spaces.
#
# Estructura esperada en el repo del Space:
#   space-repo/
#   ├── Dockerfile                ← este archivo
#   └── backend/                  ← carpeta backend completa de este proyecto
#       ├── main.py, ...
#       └── data/
#           └── predicciones_contaminantes.csv
#
# HF Spaces (SDK = Docker) construye y arranca este contenedor automáticamente.

FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema (lxml necesita build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Capa cacheable de requirements
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Código del backend + CSV de previsiones
COPY backend /app/backend

# HF Spaces enruta tráfico HTTP al puerto 7860 por defecto
EXPOSE 7860

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
