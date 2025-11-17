-- Creiamo un tipo personalizzato per essere sicuri che la direzione del trade sia solo BUY o SELL
CREATE TYPE trade_type AS ENUM ('BUY', 'SELL');

-- Creiamo la nostra tabella principale per registrare le operazioni
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    symbol VARCHAR(20) NOT NULL,
    type trade_type NOT NULL,
    quantity DECIMAL(18, 8) NOT NULL,
    price DECIMAL(18, 8) NOT NULL,
    total_cost DECIMAL(18, 8) NOT NULL,
    reason TEXT, -- Qui scriveremo perché abbiamo fatto il trade (es. "RSI < 30 e sentiment positivo")
    pnl DECIMAL(18, 8), -- Profit and Loss, verrà aggiornato quando chiudiamo la posizione
    is_open BOOLEAN DEFAULT TRUE NOT NULL
);

-- Creiamo un indice sulla colonna del simbolo per velocizzare le ricerche
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_is_open ON trades(is_open);

-- Inseriamo un'operazione di esempio per verificare che tutto funzioni
INSERT INTO trades (symbol, type, quantity, price, total_cost, reason) VALUES
('BTC/USDT', 'BUY', 0.01, 65000.0, 650.0, 'Test iniziale del sistema di logging.');