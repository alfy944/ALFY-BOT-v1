FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Esponiamo la porta 8080 (quella che ti piace)
EXPOSE 8080

# Healthcheck sulla porta giusta
HEALTHCHECK CMD curl --fail http://localhost:8080/_stcore/health || exit 1

# Avviamo Streamlit sulla 8080
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]
