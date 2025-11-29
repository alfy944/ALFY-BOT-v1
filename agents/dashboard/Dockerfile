FROM python:3.10-slim

WORKDIR /app

# Installiamo le dipendenze necessarie (httpx è fondamentale)
RUN pip install fastapi uvicorn httpx requests websockets

COPY main.py .

CMD ["python", "main.py"]
