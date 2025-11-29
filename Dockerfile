FROM python:3.10-slim

WORKDIR /app

# Installiamo git e libgomp1 (per Prophet)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copiamo i requirements
COPY requirements.txt .

# Aggiorniamo pip e installiamo le dipendenze
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiamo il codice
COPY . .

# Creiamo cartelle dati
RUN mkdir -p /app/data /app/logs

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "main.py"]
