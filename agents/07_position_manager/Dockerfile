FROM python:3.10-slim

WORKDIR /app

# Librerie per Bybit e API
RUN pip install fastapi uvicorn pybit pydantic requests

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
