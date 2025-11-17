# Usa un'immagine Python ufficiale e leggera
FROM python:3.10-slim

# Imposta la cartella di lavoro all'interno del container
WORKDIR /app

# Copia il file dei requisiti per primo, per sfruttare la cache di Docker
COPY requirements.txt .

# Installa le dipendenze Python elencate nel file requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# COMANDO CHIAVE: Scarica i corpora (dizionari/modelli) necessari per TextBlob.
# Questo comando viene eseguito dopo che textblob è stato installato da pip.
RUN python -m textblob.download_corpora

# Copia il codice sorgente dell'agente nel container
COPY main.py .

# Comando per avviare l'applicazione API quando il container parte
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]