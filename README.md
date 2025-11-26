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
