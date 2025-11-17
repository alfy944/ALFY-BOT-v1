services:
  # --- SERVIZIO 1: IL DATABASE (LA MEMORIA) ---
  db:
    image: postgres:13-alpine
    container_name: trading_db
    environment:
      POSTGRES_USER: trading_user
      POSTGRES_PASSWORD: your_strong_password_here # <-- CAMBIA QUESTA PASSWORD!
      POSTGRES_DB: trading_data
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db_init:/docker-entrypoint-initdb.d
    ports:
      - "5433:5432" # Porta per connettersi al DB dal tuo Mac (es. con un client SQL)
    restart: always

  # --- SERVIZIO 2: IL MOTORE DEI WORKFLOW ---
  n8n:
    image: n8nio/n8n
    container_name: n8n_workflow_engine
    ports:
      - "5678:5678"
    volumes:
      - n8n_data:/home/node/.n8n
    restart: always

  # --- SERVIZIO 3: L'ANALISTA TECNICO (IL CERVELLO) ---
  technical-analyzer-agent:
    build: ./agents/01_technical_analyzer
    container_name: technical-analyzer-agent
    ports:
      - "8001:8000"
    restart: always

  # --- SERVIZIO 4: L'ANALISTA DI NEWS (GLI OCCHI) ---
  news-sentiment-agent:
    build: ./agents/02_news_sentiment
    container_name: news-sentiment-agent
    ports:
      - "8002:8000"
    restart: always

  # --- SERVIZIO 5: IL GUARDIANO DEL RISCHIO ---
  trade-guardian-agent:
    build: ./agents/03_trade_guardian
    container_name: trade-guardian-agent
    ports:
      - "8003:8000"
    restart: always

  # --- SERVIZIO 6: L'ESECUTORE (LE MANI) ---
  bybit-executor:
    build: ./agents/04_bybit_executor
    container_name: bybit-executor
    env_file: # <--- LEGGE I SEGRETI DAL FILE .env
      - ./.env
    ports:
      - "8004:8000"
    restart: always
    depends_on: # <--- Si assicura che il DB sia partito prima di lui
      - db

# --- DEFINIZIONE DEI VOLUMI PER LA PERSISTENZA DEI DATI ---
volumes:
  postgres_data:
  n8n_data: