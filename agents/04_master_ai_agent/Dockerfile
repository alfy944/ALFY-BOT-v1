FROM python:3.10-slim

WORKDIR /app

# Installiamo OpenAI e FastAPI
RUN pip install fastapi uvicorn openai pydantic requests

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
