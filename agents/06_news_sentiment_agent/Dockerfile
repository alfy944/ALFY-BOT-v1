FROM python:3.9-slim

WORKDIR /app

# Installa le dipendenze di sistema
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Copia i requisiti e installa
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir textblob

# Scarica i corpora di textblob (necessari per l'analisi)
RUN python -m textblob.download_corpora

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
