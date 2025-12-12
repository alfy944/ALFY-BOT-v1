# 🤖 Trading Agent System v2.1 (Production Ready)

Sistema di trading automatico multi-agente per crypto su Bybit, alimentato da **GPT-5.1**.

## ✨ Ottimizzazioni v2.1

| Componente | Ottimizzazione |
|------------|---------------|
| Master AI | `httpx` async invece di `requests` sync |
| Sentiment | Cache 15min + batch fetch (1 API call per tutte le crypto) |
| Orchestrator | Chiama `/refresh_all` una volta per scan |

**Risultato**: ~2.880 chiamate CoinGecko/mese invece di ~28.800 (10x risparmio)

## 🚀 Quick Start

```bash
# 1. Configura API keys
nano .env

# 2. Avvia
docker-compose up -d

# 3. Monitora
docker-compose logs -f orchestrator
```

## 🖥️ Guida completa: configurazione e avvio su VPS Linux

1) **Prerequisiti minimi**
   - VPS con Ubuntu/Debian recenti, 2 vCPU / 4 GB RAM consigliati.
   - Porte libere: 8001-8008, 8010, 8080 (puoi chiuderle con un reverse proxy o firewall se non ti servono esposte).
   - Utente con permessi sudo.

2) **Installa Docker e Docker Compose plugin**
   ```bash
   sudo apt update && sudo apt install -y ca-certificates curl gnupg
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
     $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   sudo usermod -aG docker $USER
   newgrp docker
   ```

3) **Clona il progetto e prepara l'ambiente**
   ```bash
   git clone https://github.com/tuo-account/ALFY-BOT-v1.git
   cd ALFY-BOT-v1
   cp .env.example .env
   ```

4) **Compila le variabili d'ambiente**
   - Bybit: `BYBIT_API_KEY`, `BYBIT_API_SECRET`, opzionale `BYBIT_TESTNET=true` per ambiente demo.
   - DeepSeek: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL` per l'agente Master e Learning.
   - CoinGecko: `COINGECKO_API_KEY` per il sentiment cache/batch. 【F:.env.example†L1-L34】
   - Parametri trading: leva, size percentuali, intervalli e trailing stop personalizzabili (`SIZE_PCT`, `MAX_POSITION_SIZE_PCT`, `SCAN_INTERVAL`, ecc.). 【F:.env.example†L15-L34】

5) **Avvia tutti i servizi**
   ```bash
   docker compose up -d
   ```
   Questo builda e lancia l'orchestrator, gli analyzer tecnici, i micro-servizi di sentiment/forecast, il master AI, il position manager e la dashboard React. 【F:docker-compose.yml†L1-L71】

6) **Verifica lo stato**
   - Log orchestrator: `docker compose logs -f orchestrator`
   - Healthcheck servizi (esempio technical analyzer): `curl http://localhost:8001/health`
   - Dashboard: apri `http://<IP_VPS>:8080` nel browser.

7) **Gestione operativa**
   - Fermare: `docker compose down` (mantiene i volumi condivisi).
   - Aggiornare il codice: `git pull` e poi `docker compose build --no-cache && docker compose up -d`.
   - Backup dati: i file condivisi (report decisioni, strategie evolutive) sono nel volume `shared_data`; puoi montarli su host aggiungendo un bind nel `docker-compose.yml` se vuoi esportarli.

8) **Sicurezza**
   - Imposta firewall per limitare le porte pubbliche; esponi solo la dashboard o proteggila con un reverse proxy/autenticazione.
   - Conserva `.env` in modo sicuro e non committarlo nel repository.
   - Testa sempre con `BYBIT_TESTNET=true` prima di passare a produzione. 【F:README.md†L29-L33】

## 🧭 Come funziona ora l'orchestrator

- **Universo simboli dinamico**: per default il ciclo di scansione usa i perpetual USDT di Bybit con il turnover a 24h più alto (endpoint `v5/market/tickers`, categoria `linear`). Il limite è regolabile con `TRENDING_SYMBOLS_LIMIT` (default `6`). Se `USE_TRENDING_SYMBOLS=false` o la chiamata fallisce, rientra sui tre simboli storici `BTCUSDT`, `ETHUSDT`, `SOLUSDT`.
- **Gestione posizioni**: a ogni ciclo (default 60s) interroga il Position Manager per saldo e posizioni aperte, effettua un check di perdite critiche (`REVERSE_THRESHOLD`) e salva un riepilogo su `/data/ai_decisions.json` per la dashboard.
- **Pipeline decisionale**: se c'è almeno uno slot libero (`MAX_POSITIONS=3`), filtra i simboli senza posizione aperta, chiama l'analisi tecnica multi-timeframe per ciascuno e passa i risultati al Master AI (`/decide_batch`). Gli ordini di apertura long/short approvati vengono inviati al Position Manager con leva e size percentuale suggerite.

## 📊 Endpoints

| Servizio | URL |
|----------|-----|
| Technical | http://localhost:8001/health |
| Fibonacci | http://localhost:8002/health |
| Gann | http://localhost:8003/health |
| Sentiment | http://localhost:8004/health |
| Sentiment Cache | http://localhost:8004/cache_status |
| Master AI | http://localhost:8005/latest_decisions |
| Position Manager | http://localhost:8006/get_open_positions |

## ⚠️ Importante

- Testa con `BYBIT_TESTNET=true`
- Modello AI: GPT-5.1
