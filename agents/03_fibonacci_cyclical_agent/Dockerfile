# Usa un'immagine Python ufficiale come base
FROM python:3.10-slim

# Imposta la cartella di lavoro all'interno del container
WORKDIR /app

# Copia il file delle dipendenze
COPY requirements.txt .

# Installa le dipendenze Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il resto del codice sorgente (incluso main.py)
COPY . .

# Esponi la porta su cui l'agente ascolterà
EXPOSE 8000

# Il comando per avviare l'agente quando il container parte
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
