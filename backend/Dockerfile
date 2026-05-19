FROM python:3.11-slim

WORKDIR /app

# Dependencias de sistema mínimas (lxml, scipy, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código del paquete backend (esperado en /app/backend/)
COPY . ./backend

EXPOSE 7860

# Hugging Face Spaces espera puerto 7860 por defecto
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
