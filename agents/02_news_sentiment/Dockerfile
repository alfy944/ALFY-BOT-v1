FROM python:3.10-slim
WORKDIR /app

# Copia e installa le dipendenze Python direttamente
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Scarica i corpora necessari per textblob
RUN python -m textblob.download_corpora

# Copia il codice dell'applicazione
COPY main.py .

# Comando di avvio
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
