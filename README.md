# 🤖 Trading Agent System v3.0 (DeepSeek AI + Advanced Strategy)

Sistema di trading automatico multi-agente per crypto su Bybit, alimentato da **DeepSeek AI**.

## ✨ Nuove Funzionalità v3.0

| Componente | Funzionalità |
|------------|--------------|
| **DeepSeek LLM** | Modello AI avanzato per decisioni autonome |
| **Reverse Strategy** | Inversione automatica posizioni perdenti con recupero perdite |
| **Learning Agent** | Analisi storica trade per miglioramento continuo (machine learning) |
| **Database Tracking** | Tracciamento completo di tutte le operazioni chiuse |
| **Position Monitor** | Monitoraggio ogni 60 secondi con trailing stop dinamico |
| **Loss Recovery** | Sistema proporzionale per recuperare perdite precedenti |

## 🎯 Strategia Reverse Automatica

Il sistema monitora continuamente le posizioni aperte:
- **Threshold**: Quando una posizione perde oltre il 2% (configurabile)
- **Azione**: Chiude la posizione perdente e apre immediatamente la posizione opposta
- **Recovery**: Aumenta la size della nuova posizione per recuperare la perdita (moltiplicatore configurabile)
- **Esempio**: Perdita $100 su LONG → Chiude LONG → Apre SHORT con size 1.5x per recuperare

## 🧠 Learning Agent

Agente dedicato che analizza lo storico dei trade per:
- Identificare pattern di successo e errori comuni
- Suggerire quali symbol e direzioni hanno performato meglio
- Fornire raccomandazioni basate su dati storici
- Migliorare continuamente la strategia di trading

## 📊 Architettura

```
┌─────────────────┐
│  Orchestrator   │ ← Coordina tutto ogni 60s
└────────┬────────┘
         │
    ┌────┴─────────────────────────────┐
    │                                   │
┌───▼────────┐  ┌────────────┐  ┌─────▼────────┐
│ Position   │  │ DeepSeek   │  │  Learning    │
│ Manager    │  │    AI      │  │   Agent      │
│ (60s loop) │  │ (Autonomo) │  │  (History)   │
└────────────┘  └────────────┘  └──────────────┘
     │               │                  │
     └───────────────┴──────────────────┘
              Database SQLite

## 🚀 Quick Start

```bash
# 1. Configura API keys
nano .env

# Richieste:
# - DEEPSEEK_API_KEY
# - BYBIT_API_KEY
# - BYBIT_API_SECRET

# 2. Crea directory dati
mkdir -p data

# 3. Avvia
docker-compose up -d

# 4. Monitora
docker-compose logs -f orchestrator
```

## 🔧 Configurazione

### .env File Essenziale

```bash
# DeepSeek API (NUOVO)
DEEPSEEK_API_KEY=your_deepseek_key_here
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com

# Bybit API
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=true  # Usa true per testare

# Trading Settings
MIN_CONFIDENCE=60
LEVERAGE_SCALP=5
LEVERAGE_SWING=3
SIZE_PCT=0.15
MAX_POSITION_SIZE_PCT=0.30

# Reverse Strategy (NUOVO)
ENABLE_REVERSE_STRATEGY=true
REVERSE_LOSS_THRESHOLD_PCT=2.0      # Attiva reverse al 2% di perdita
REVERSE_RECOVERY_MULTIPLIER=1.5     # Aumenta size di 1.5x per recupero

# Trailing Stop
ENABLE_TRAILING_STOP=true
TRAILING_ACTIVATION_PCT=1.8
TRAILING_CALLBACK_PCT=1.0

# Intervals
SCAN_INTERVAL=15         # Analisi AI ogni 15 minuti
MONITOR_INTERVAL=60      # Position check ogni 60 secondi
```

## 📊 Endpoints

| Servizio | URL | Descrizione |
|----------|-----|-------------|
| Technical | http://localhost:8001/health | Analisi tecnica |
| Fibonacci | http://localhost:8002/health | Livelli Fibonacci |
| Gann | http://localhost:8003/health | Analisi Gann |
| DeepSeek AI | http://localhost:8004/health | Motore decisionale AI |
| Gann Analyzer | http://localhost:8005/health | Analizzatore Gann |
| Sentiment | http://localhost:8006/health | Sentiment analysis |
| Position Manager | http://localhost:8007/get_open_positions | Gestione posizioni |
| Forecaster | http://localhost:8008/health | Previsioni |
| Learning Agent | http://localhost:8010/get_insights | **NUOVO**: Analisi storica |
| Dashboard | http://localhost:8080 | UI principale |

### Nuovi Endpoints Learning Agent

- `GET /get_insights` - Ottieni insights generali
- `POST /analyze_symbols` - Analizza simboli specifici
- `GET /common_mistakes` - Errori comuni da evitare
- `GET /best_patterns` - Pattern più redditizi

### Nuovi Endpoints Position Manager

- `POST /reverse_position` - Esegui reverse strategy su posizione
- `GET /get_closed_positions` - Ottieni storico posizioni dal database
- `GET /management_logs` - Log gestione posizioni

## 🎮 Come Funziona

1. **Ogni 60 secondi**:
   - Position Manager verifica posizioni aperte
   - Aggiorna trailing stop per proteggere profitti
   - Orchestrator controlla se attivare reverse strategy su perdite

2. **Ogni 15 minuti**:
   - Orchestrator richiede analisi a tutti gli agenti tecnici
   - Learning Agent fornisce insights storici
   - DeepSeek AI valuta autonomamente e decide le azioni
   - Execution automatica delle decisioni

3. **Reverse Strategy**:
   - Trigger: Posizione perde oltre 2% (configurabile)
   - Azione: Chiude posizione → Apre opposta con size maggiorata
   - Obiettivo: Recuperare perdita + profitto

## ⚠️ Importante

- **SEMPRE** testa prima con `BYBIT_TESTNET=true`
- Modello AI: DeepSeek (autonomo e decisionale)
- Database SQLite: `/data/trading_history.db`
- Backup automatico equity ogni 60s
- Learning continuo da storico trade
