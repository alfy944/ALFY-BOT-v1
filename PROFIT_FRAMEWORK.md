# ProFiT Framework Implementation

## Overview

This implementation adds the ProFiT (Program Search for Financial Trading) framework to the trading agent system. The Learning Agent (10) automatically evolves trading strategies every 48 hours and updates parameters used by the Master AI (04).

## Architecture

```
Learning Agent (10) - ProFiT Enhanced
│
├── 📊 DATA COLLECTION (continuous)
│   └── Saves every trade: entry, exit, PnL, market conditions
│
├── 🧬 EVOLUTION (every 48 hours)
│   ├── Analyzes performance of last 48 hours
│   ├── Asks DeepSeek: "How to improve?"
│   ├── Generates new mutated strategy
│   ├── Backtests on collected data
│   └── If better → Updates Master AI parameters
│
└── 💾 STRATEGY ARCHIVE
    └── Maintains the best strategies found
```

## Components

### 1. Learning Agent (Agent 10)
- **Location**: `agents/10_learning_agent/`
- **Port**: 8010
- **Functionality**:
  - Records all trade history
  - Runs evolution cycle every 48 hours
  - Calculates performance metrics
  - Queries DeepSeek for strategy improvements
  - Backtests new strategies
  - Saves evolved parameters to shared volume

### 2. Master AI (Agent 04) - Enhanced
- **Location**: `agents/04_master_ai_agent/`
- **Port**: 8004
- **New Features**:
  - Hot-reloads evolved parameters on each request
  - Includes evolved parameters in trading decisions
  - Falls back to defaults if no evolved params exist

### 3. Shared Data Volume
- **Location**: `/data` (Docker volume)
- **Files**:
  - `evolved_params.json` - Current evolved parameters
  - `trading_history.json` - All recorded trades
  - `evolution_log.json` - Evolution cycle logs
  - `strategy_archive/` - Archived strategy versions

## API Endpoints

### Learning Agent (Port 8010)

#### `POST /record_trade`
Record a completed trade for analysis.

**Request**:
```json
{
  "timestamp": "2025-12-09T10:00:00",
  "symbol": "BTCUSDT",
  "side": "LONG",
  "entry_price": 50000.0,
  "exit_price": 51000.0,
  "pnl_pct": 2.0,
  "leverage": 5.0,
  "size_pct": 0.15,
  "duration_minutes": 60,
  "market_conditions": {}
}
```

#### `POST /trigger_evolution`
Manually trigger an evolution cycle (useful for testing).

#### `GET /current_params`
Get current evolved parameters.

**Response**:
```json
{
  "status": "evolved",
  "version": "v1.5",
  "params": {
    "rsi_overbought": 65,
    "rsi_oversold": 35,
    "default_leverage": 6,
    ...
  },
  "evolved_at": "2025-12-09T10:00:00"
}
```

#### `GET /performance`
Get recent performance metrics.

#### `GET /evolution_log`
Get recent evolution log entries.

#### `GET /health`
Health check endpoint.

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# ProFiT Evolution Settings
EVOLUTION_INTERVAL_HOURS=48          # Evolution frequency (48 hours = 2 days)
MIN_TRADES_FOR_EVOLUTION=5           # Minimum trades needed to evolve
BACKTEST_IMPROVEMENT_THRESHOLD=0.5   # Minimum PnL improvement % to accept
MAX_STRATEGY_ARCHIVE=20              # Max archived strategies to keep
```

## Evolved Parameters

The following parameters are automatically optimized:

```python
{
    "rsi_overbought": 70,      # RSI threshold for short (60-80)
    "rsi_oversold": 30,        # RSI threshold for long (20-40)
    "default_leverage": 5,     # Default leverage (1-10)
    "size_pct": 0.15,          # % of wallet per trade (0.05-0.25)
    "reverse_threshold": 2.0,  # % loss for position reverse (0.5-5.0)
    "atr_multiplier_sl": 2.0,  # Stop loss multiplier (1.0-4.0)
    "atr_multiplier_tp": 3.0,  # Take profit multiplier (1.5-6.0)
    "min_rsi_for_long": 40,    # Min RSI to open long (30-50)
    "max_rsi_for_short": 60    # Max RSI to open short (50-70)
}
```

## Deployment

### Start Services

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f 10_learning_agent
docker-compose logs -f 04_master_ai_agent
```

### Verify Setup

```bash
# Check learning agent health
curl http://localhost:8010/health

# Check current parameters
curl http://localhost:8010/current_params

# Check master AI is using evolved params
docker-compose logs 04_master_ai_agent | grep "evolved params"
```

## Expected Log Output

### Evolution Cycle (every 48 hours)

```
[2025-12-11 00:00] 🧬 PROFIT EVOLUTION START
📊 Analyzing last 48 hours: 15 trades
📈 Current performance:
   - Win rate: 47%
   - Total PnL: -2.3%
   - Max drawdown: -4.1%

🤖 Asking DeepSeek for improvements...
💡 DeepSeek suggests:
   - rsi_overbought: 70 → 65 (more aggressive entries)
   - size_pct: 0.15 → 0.12 (reduce risk after losses)
   - default_leverage: 5 → 4 (conservative due to drawdown)

🧪 Backtesting new strategy on 15 trades...
📊 Backtest result:
   - Win rate: 53% (+6%)
   - Total PnL: +1.8% (+4.1%)
   - Max drawdown: -2.8% (improved)

✅ Evolution successful!
💾 Saved: /data/evolved_params.json (v1.3)
📁 Archived: /data/strategy_archive/strategy_v1.3.json
🔄 Master AI will use new params from next cycle

[2025-12-11 00:01] Master AI: 📚 Using evolved params v1.3
```

## Monitoring

### Check Evolution Status

```bash
# View recent performance
curl http://localhost:8010/performance

# View evolution log
curl http://localhost:8010/evolution_log

# View current evolved parameters
curl http://localhost:8010/current_params
```

### Manual Evolution Trigger

For testing or immediate evolution:

```bash
curl -X POST http://localhost:8010/trigger_evolution
```

## Data Persistence

All data is stored in the `shared_data` Docker volume:

```bash
# Inspect volume
docker volume inspect trading-agent-system_shared_data

# Backup data
docker run --rm -v trading-agent-system_shared_data:/data -v $(pwd):/backup alpine tar czf /backup/profit_data_backup.tar.gz /data

# Restore data
docker run --rm -v trading-agent-system_shared_data:/data -v $(pwd):/backup alpine tar xzf /backup/profit_data_backup.tar.gz -C /
```

## Troubleshooting

### No Evolution Happening

1. Check if enough trades recorded:
   ```bash
   curl http://localhost:8010/performance
   ```

2. Check evolution interval:
   ```bash
   docker-compose logs 10_learning_agent | grep "evolution loop"
   ```

3. Manually trigger evolution:
   ```bash
   curl -X POST http://localhost:8010/trigger_evolution
   ```

### Master AI Not Using Evolved Params

1. Check if evolved_params.json exists:
   ```bash
   docker exec 04_master_ai_agent ls -la /data/
   ```

2. Check Master AI logs:
   ```bash
   docker-compose logs 04_master_ai_agent | grep "evolved params"
   ```

3. If file exists but not loading, check permissions:
   ```bash
   docker exec 04_master_ai_agent cat /data/evolved_params.json
   ```

### Evolution Failing

1. Check DeepSeek API:
   ```bash
   docker-compose logs 10_learning_agent | grep "DeepSeek"
   ```

2. Check for errors:
   ```bash
   docker-compose logs 10_learning_agent | grep "Error"
   ```

## Integration with Existing System

The ProFiT framework integrates seamlessly with the existing trading system:

1. **No changes required** to other agents
2. **Master AI** automatically uses evolved parameters (hot-reload)
3. **Trade recording** can be added to position manager (optional)
4. **Backward compatible** - works with default parameters if evolution disabled

## Future Enhancements

Potential improvements:

1. Multi-objective optimization (win rate + PnL + drawdown)
2. Ensemble strategies (combine multiple evolved strategies)
3. Market regime detection (different params for different market conditions)
4. Real-time parameter adjustment (not just every 48 hours)
5. A/B testing framework (compare strategies in parallel)
6. Integration with position manager for automatic trade recording

## License

Same as main project.
