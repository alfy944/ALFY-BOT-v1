# ✅ Checklist di Attivazione Sistema

## 🎯 Pre-Requisiti

### API Keys Necessarie
- [ ] **DeepSeek API Key** - Ottieni da: https://platform.deepseek.com/
- [ ] **Bybit API Key** - Ottieni da: https://www.bybit.com/app/user/api-management
- [ ] **Bybit API Secret** - Generato insieme alla API Key

### Permessi Bybit API
Assicurati che la tua Bybit API Key abbia i seguenti permessi:
- [ ] Read - Per leggere posizioni e balance
- [ ] Trade - Per aprire/chiudere posizioni
- [ ] ❌ Withdraw - NON necessario (per sicurezza)

### Sistema
- [ ] Docker installato
- [ ] Docker Compose installato
- [ ] Porta 8080 disponibile (dashboard)
- [ ] Almeno 2GB RAM liberi
- [ ] Connessione internet stabile

## 📝 Configurazione

### Step 1: Clona e Prepara
```bash
# Se non ancora fatto
git clone https://github.com/lcz79/trading-agent-system.git
cd trading-agent-system

# Checkout del branch con le nuove features
git checkout copilot/implement-deepseek-llm-strategy

# Crea directory data
mkdir -p data
```

### Step 2: Configura .env
```bash
# Copia il template
cp .env.example .env

# Modifica con le tue chiavi
nano .env  # o usa il tuo editor preferito
```

### Step 3: Compila .env File
```bash
# ========================================
# DEEPSEEK API (OBBLIGATORIO)
# ========================================
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxx  # ← Inserisci qui
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com

# ========================================
# BYBIT API (OBBLIGATORIO)
# ========================================
BYBIT_API_KEY=xxxxxxxxxxxxxxxxxxxxx        # ← Inserisci qui
BYBIT_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxx   # ← Inserisci qui
BYBIT_TESTNET=true                          # ← IMPORTANTE: Usa true per test!

# ========================================
# TRADING SETTINGS
# ========================================
MIN_CONFIDENCE=60
LEVERAGE_SCALP=5
LEVERAGE_SWING=3
SIZE_PCT=0.15
MAX_LEVERAGE=10
MAX_POSITION_SIZE_PCT=0.30

# ========================================
# REVERSE STRATEGY
# ========================================
ENABLE_REVERSE_STRATEGY=true
REVERSE_LOSS_THRESHOLD_PCT=2.0      # Reverse a 2% di perdita
REVERSE_RECOVERY_MULTIPLIER=1.5     # Size x1.5 per recupero

# ========================================
# TRAILING STOP
# ========================================
ENABLE_TRAILING_STOP=true
TRAILING_ACTIVATION_PCT=1.8
TRAILING_CALLBACK_PCT=1.0

# ========================================
# INTERVALS
# ========================================
SCAN_INTERVAL=15
MONITOR_INTERVAL=60
LEARNING_INTERVAL=3600

# ========================================
# DATABASE
# ========================================
DB_PATH=./data/trading_history.db
```

### Step 4: Verifica Configurazione
- [ ] DEEPSEEK_API_KEY impostata
- [ ] BYBIT_API_KEY impostata
- [ ] BYBIT_API_SECRET impostata
- [ ] BYBIT_TESTNET=true (per test)
- [ ] ENABLE_REVERSE_STRATEGY=true
- [ ] File .env salvato correttamente

## 🚀 Avvio Sistema

### Test Mode (CONSIGLIATO PRIMA)
```bash
# Avvia con testnet
docker-compose up -d

# Verifica che tutti i container siano attivi
docker-compose ps

# Dovresti vedere:
# - 01_technical_analyzer
# - 03_fibonacci_agent
# - 04_master_ai_agent (DeepSeek)
# - 05_gann_analyzer_agent
# - 06_news_sentiment_agent
# - 07_position_manager
# - 08_forecaster_agent
# - 10_learning_agent (NUOVO)
# - orchestrator
# - dashboard
```

### Verifica Logs
```bash
# Orchestrator (cervello del sistema)
docker-compose logs -f orchestrator

# Cerca questi messaggi di conferma:
# ✅ "Trading Orchestrator Starting..."
# ✅ "Position monitoring: every 60 seconds"
# ✅ "Reverse strategy: ENABLED"
# ✅ "DeepSeek AI..." (nelle analisi)
```

### Verifica Dashboard
```bash
# Apri browser su:
http://localhost:8080

# Dovresti vedere:
# ✅ NET EQUITY
# ✅ ACTIVE ENGAGEMENTS
# ✅ SYSTEM ONLINE (verde)
```

## 🧪 Test Funzionalità

### 1. Verifica DeepSeek AI
```bash
# Test endpoint
curl http://localhost:8004/health

# Risposta attesa:
# {"status":"active","model":"deepseek-chat"}
```

### 2. Verifica Learning Agent
```bash
# Test insights
curl http://localhost:8010/get_insights

# Risposta attesa (JSON con insights)
```

### 3. Verifica Position Manager
```bash
# Test posizioni
curl http://localhost:8007/get_open_positions

# Risposta attesa:
# {"active":[],"details":[]}
```

### 4. Verifica Database
```bash
# Controlla che il DB sia stato creato
ls -lh data/trading_history.db

# Se esiste, tutto ok!
```

## 📊 Monitoring 24h (TEST MODE)

### Checklist Giornaliera
- [ ] Controlla logs ogni 3-4 ore
- [ ] Verifica che non ci siano errori ripetuti
- [ ] Monitora se vengono aperte posizioni (su testnet)
- [ ] Controlla learning agent insights dopo qualche trade

### Comandi Utili
```bash
# Logs in tempo reale
docker-compose logs -f orchestrator

# Errori recenti
docker-compose logs --tail=100 orchestrator | grep -i error

# Status containers
docker-compose ps

# Restart se necessario
docker-compose restart orchestrator

# Stop completo
docker-compose down
```

## 🎮 Passaggio a Produzione

### ⚠️ ATTENZIONE: Solo DOPO test di 24h+

### Step 1: Backup
```bash
# Backup database
cp data/trading_history.db data/trading_history.db.backup

# Backup .env
cp .env .env.backup
```

### Step 2: Modifica .env
```bash
nano .env

# Cambia:
BYBIT_TESTNET=false  # ← Da true a false

# Riduci leverage se vuoi essere più conservativo:
LEVERAGE_SCALP=3
LEVERAGE_SWING=2
SIZE_PCT=0.10  # Riduci da 0.15 a 0.10 se preferisci
```

### Step 3: Riavvia
```bash
docker-compose down
docker-compose up -d

# Verifica logs
docker-compose logs -f orchestrator

# Cerca:
# "Testnet: False" o simile
```

### Step 4: Monitoring Intensivo
- [ ] Prima ora: Check ogni 15 minuti
- [ ] Primo giorno: Check ogni 2 ore
- [ ] Prima settimana: Check giornaliero

## 🔧 Tuning Parametri

### Se vuoi essere PIÙ CONSERVATIVO
```bash
# In .env
REVERSE_LOSS_THRESHOLD_PCT=3.0      # Reverse solo a 3%
REVERSE_RECOVERY_MULTIPLIER=1.2     # Recovery più conservativo
SIZE_PCT=0.10                        # Size più piccola
LEVERAGE_SCALP=3                     # Leva ridotta
```

### Se vuoi essere PIÙ AGGRESSIVO
```bash
# In .env
REVERSE_LOSS_THRESHOLD_PCT=1.5      # Reverse prima
REVERSE_RECOVERY_MULTIPLIER=2.0     # Recovery maggiore
SIZE_PCT=0.20                        # Size maggiore
LEVERAGE_SCALP=7                     # Leva maggiore
```

## 📈 Performance Review

### Dopo 1 Settimana
```bash
# Controlla learning agent
curl http://localhost:8010/common_mistakes

# Controlla closed positions
sqlite3 data/trading_history.db "SELECT symbol, COUNT(*), AVG(pnl), SUM(pnl) FROM closed_positions GROUP BY symbol;"

# Aggiusta parametri basandoti sui dati
```

## ❌ Troubleshooting

### Container non si avvia
```bash
# Check logs
docker-compose logs master-ai-agent

# Possibile causa: DEEPSEEK_API_KEY mancante
# Soluzione: Verifica .env
```

### Errore "API Key Invalid"
```bash
# Test DeepSeek key manualmente
curl -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
     https://api.deepseek.com/v1/models
```

### Database locked
```bash
docker-compose down
rm data/trading_history.db-journal
docker-compose up -d
```

### Reverse non si attiva
```bash
# Verifica configurazione
docker-compose logs orchestrator | grep "ENABLE_REVERSE"

# Dovrebbe mostrare: "Reverse strategy: ENABLED"
```

## 📞 Support & Resources

### Documentazione
- 📖 `README.md` - Overview e quick start
- 🏗️ `ARCHITECTURE.md` - Architettura dettagliata
- 📝 `IMPLEMENTATION_SUMMARY.md` - Guida implementazione

### Logs Importanti
```bash
# Orchestrator (decisioni)
docker-compose logs -f orchestrator

# DeepSeek AI (reasoning)
docker-compose logs -f 04_master_ai_agent

# Position Manager (esecuzioni)
docker-compose logs -f 07_position_manager

# Learning Agent (insights)
docker-compose logs -f 10_learning_agent
```

### Endpoints di Test
- http://localhost:8080 - Dashboard
- http://localhost:8004/health - DeepSeek AI
- http://localhost:8007/get_open_positions - Posizioni
- http://localhost:8010/get_insights - Learning

## ✅ Checklist Finale

Prima di considerare il sistema "pronto":

### Test Mode
- [ ] Sistema attivo per 24h+ senza errori critici
- [ ] Almeno 5 trade eseguiti su testnet
- [ ] Learning agent genera insights
- [ ] Database popola correttamente
- [ ] Reverse strategy testata (se triggherata)
- [ ] Dashboard accessibile e aggiornata

### Production Mode
- [ ] Backup configurazione fatto
- [ ] BYBIT_TESTNET=false
- [ ] Monitoring attivo prima ora
- [ ] Capital allocation decisa (quanto investire)
- [ ] Stop-loss manuale di sicurezza pianificato
- [ ] Contatto con exchange verificato

## 🎉 Sistema Pronto!

Una volta completata questa checklist, il tuo trading agent system è:
- ✅ Configurato con DeepSeek AI
- ✅ Reverse strategy attiva
- ✅ Learning agent operativo
- ✅ Database tracking completo
- ✅ Monitoring 60 secondi
- ✅ Sicuro e testato

**Buon trading! 🚀**

---

*Nota: Questo è un sistema automatico. Monitora regolarmente e ajusta parametri secondo necessità.*
