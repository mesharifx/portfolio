# Python Trading Core — Code Sample

A short, self-contained sample of how I structure trading software in Python:
one exchange interface, a Binance Spot Testnet connector, and a risk manager
that checks every order before it reaches the exchange.

It is a style and structure sample, not a full product.

## What it shows

- **One `Exchange` interface**: Binance, Bybit or any other venue plugs in the same way.
- **`BinanceTestnet`**: signed REST requests (HMAC-SHA256), prices, balances,
  market / limit / stop-limit orders and cancel. API keys are read from
  environment variables, never hard-coded.
- **`RiskManager`**: position sizing from % risk and stop distance, mandatory
  stop loss, wrong-side stop check, and a daily loss limit measured from the
  day's starting equity (resets each day).
- **`OrderManager`**: validates every order, runs the risk checks, then sends it.
- **`PaperExchange`**: run and test everything with no API keys.

## Run it

```bash
pip install requests
python trading_core_sample.py      # paper-mode demo
python test_sample.py              # risk and order logic tests
python test_binance_mock.py        # request building, signing, error handling
```

To use the Binance Spot Testnet, set `BINANCE_TESTNET_KEY` and
`BINANCE_TESTNET_SECRET` with testnet keys (no real funds).

## Tests

- Position sizing, rejected orders (no stop, wrong-side stop, size above limit),
  input validation, daily loss limit and day rollover.
- Binance request building with a mocked HTTP layer: parameters, number
  formatting, HMAC signature, exchange errors and network errors.
- The signing method was checked against the example in Binance's API docs.

---
Meshari A. · Trader and trading-software developer
