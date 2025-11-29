FROM python:3.10-slim

WORKDIR /app

# Installiamo schedule per il loop temporale e requests/httpx
RUN pip install schedule requests httpx pybit textblob

COPY main.py .

CMD ["python", "main.py"]
