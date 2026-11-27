"""
Trading core sample: exchange connector + order handling + risk checks.

Code-style sample by Meshari A. (Upwork). Not the full project.
- One Exchange interface, so Binance, Bybit or others plug in the same way.
- Every order goes through RiskManager before it reaches the exchange.
- BinanceTestnet uses the official Spot Testnet REST API (no real funds).
- PaperExchange lets you run and test the logic with no API keys at all.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlencode

import requests


# ---------- Data models ----------
@dataclass
class OrderRequest:
    symbol: str
    side: str                 # "BUY" or "SELL"
    qty: float
    order_type: str = "MARKET"  # MARKET, LIMIT, STOP_LOSS_LIMIT
    price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None  # protective stop used for risk sizing


@dataclass
class OrderResult:
    ok: bool
    order_id: str | None = None
    status: str = ""
    reason: str = ""


def fmt(x: float) -> str:
    """Plain decimal string (never scientific notation like 1e-05)."""
    return f"{x:.8f}".rstrip("0").rstrip(".")


def validate(req: OrderRequest) -> str | None:
    if req.side not in ("BUY", "SELL"):
        return "side must be BUY or SELL"
    if req.qty <= 0:
        return "qty must be positive"
    if req.order_type not in ("MARKET", "LIMIT", "STOP_LOSS_LIMIT"):
        return f"unsupported order type {req.order_type}"
    if req.order_type != "MARKET" and not req.price:
        return f"{req.order_type} order needs a price"
    if req.order_type == "STOP_LOSS_LIMIT" and not req.stop_price:
        return "STOP_LOSS_LIMIT order needs a stop_price"
    return None


def _error_text(e: requests.RequestException) -> str:
    """Exchange error body if there is one (e.g. Binance code/msg), else the network error."""
    if e.response is not None:
        return f"exchange error {e.response.status_code}: {e.response.text}"
    return f"network error: {e}"


# ---------- Exchange interface ----------
class Exchange(ABC):
    @abstractmethod
    def last_price(self, symbol: str) -> float: ...

    @abstractmethod
    def balance(self, asset: str) -> float: ...

    @abstractmethod
    def place_order(self, req: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> OrderResult: ...


class BinanceTestnet(Exchange):
    """Binance Spot Testnet. Keys are read from environment variables."""

    BASE = "https://testnet.binance.vision"

    def __init__(self) -> None:
        self.key = os.environ["BINANCE_TESTNET_KEY"]
        self.secret = os.environ["BINANCE_TESTNET_SECRET"].encode()
        self.http = requests.Session()
        self.http.headers["X-MBX-APIKEY"] = self.key

    def _signed(self, method: str, path: str, params: dict) -> dict:
        params = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(params)
        sig = hmac.new(self.secret, query.encode(), hashlib.sha256).hexdigest()
        r = self.http.request(method, f"{self.BASE}{path}?{query}&signature={sig}", timeout=10)
        r.raise_for_status()
        return r.json()

    def last_price(self, symbol: str) -> float:
        r = self.http.get(f"{self.BASE}/api/v3/ticker/price", params={"symbol": symbol}, timeout=10)
        r.raise_for_status()
        return float(r.json()["price"])

    def balance(self, asset: str) -> float:
        data = self._signed("GET", "/api/v3/account", {})
        row = next((b for b in data["balances"] if b["asset"] == asset), None)
        return float(row["free"]) if row else 0.0

    def place_order(self, req: OrderRequest) -> OrderResult:
        params = {"symbol": req.symbol, "side": req.side, "type": req.order_type, "quantity": fmt(req.qty)}
        if req.order_type != "MARKET":
            params.update(price=fmt(req.price), timeInForce="GTC")
        if req.stop_price is not None:
            params["stopPrice"] = fmt(req.stop_price)
        try:
            data = self._signed("POST", "/api/v3/order", params)
            return OrderResult(True, str(data["orderId"]), data["status"])
        except requests.RequestException as e:
            return OrderResult(False, status="ERROR", reason=_error_text(e))

    def cancel_order(self, symbol: str, order_id: str) -> OrderResult:
        try:
            data = self._signed("DELETE", "/api/v3/order", {"symbol": symbol, "orderId": order_id})
            return OrderResult(True, order_id, data["status"])
        except requests.RequestException as e:
            return OrderResult(False, order_id, "ERROR", _error_text(e))


class PaperExchange(Exchange):
    """In-memory exchange for tests and dry runs."""

    def __init__(self, prices: dict[str, float], usdt: float) -> None:
        self.prices, self.balances, self._next = prices, {"USDT": usdt}, 1

    def last_price(self, symbol: str) -> float:
        return self.prices[symbol]

    def balance(self, asset: str) -> float:
        return self.balances.get(asset, 0.0)

    def place_order(self, req: OrderRequest) -> OrderResult:
        oid, self._next = str(self._next), self._next + 1
        return OrderResult(True, oid, "FILLED" if req.order_type == "MARKET" else "NEW")

    def cancel_order(self, symbol: str, order_id: str) -> OrderResult:
        return OrderResult(True, order_id, "CANCELED")


# ---------- Risk management ----------
@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 1.0   # % of equity lost if the stop is hit
    daily_loss_limit_pct: float = 3.0  # stop trading for the day after this
    require_stop_loss: bool = True


@dataclass
class RiskManager:
    cfg: RiskConfig
    day: date = field(default_factory=date.today)
    realized_pnl_today: float = 0.0
    day_start_equity: float | None = None  # daily limit is measured from this

    def _roll_day(self) -> None:
        if date.today() != self.day:
            self.day, self.realized_pnl_today, self.day_start_equity = date.today(), 0.0, None

    def record_pnl(self, pnl: float) -> None:
        self._roll_day()
        self.realized_pnl_today += pnl

    def size_position(self, equity: float, entry: float, stop: float) -> float:
        risk_amount = equity * self.cfg.risk_per_trade_pct / 100
        per_unit = abs(entry - stop)
        return 0.0 if per_unit == 0 else risk_amount / per_unit

    def check(self, req: OrderRequest, equity: float, entry: float) -> str | None:
        """Return a rejection reason, or None if the order is allowed."""
        self._roll_day()
        if self.day_start_equity is None:
            self.day_start_equity = equity
        if self.realized_pnl_today <= -self.day_start_equity * self.cfg.daily_loss_limit_pct / 100:
            return "daily loss limit reached"
        if self.cfg.require_stop_loss and req.stop_loss is None:
            return "stop loss is required"
        if req.stop_loss is not None:
            wrong_side = (req.side == "BUY" and req.stop_loss >= entry) or \
                         (req.side == "SELL" and req.stop_loss <= entry)
            if wrong_side:
                return "stop loss is on the wrong side of entry"
            max_qty = self.size_position(equity, entry, req.stop_loss)
            if req.qty > max_qty * 1.0001:
                return f"qty {req.qty} exceeds risk limit {max_qty:.6f}"
        return None


# ---------- Order manager ----------
class OrderManager:
    def __init__(self, exchange: Exchange, risk: RiskManager, quote: str = "USDT") -> None:
        self.ex, self.risk, self.quote = exchange, risk, quote

    def submit(self, req: OrderRequest) -> OrderResult:
        invalid = validate(req)
        if invalid:
            return OrderResult(False, status="REJECTED", reason=invalid)
        equity = self.ex.balance(self.quote)  # sample: free quote balance as equity
        entry = req.price or self.ex.last_price(req.symbol)
        reason = self.risk.check(req, equity, entry)
        if reason:
            return OrderResult(False, status="REJECTED", reason=reason)
        return self.ex.place_order(req)


if __name__ == "__main__":
    ex = PaperExchange({"BTCUSDT": 60000.0}, usdt=10_000)
    om = OrderManager(ex, RiskManager(RiskConfig()))
    qty = om.risk.size_position(10_000, 60000, 59400)  # 1% risk, $600 stop; 5 decimals = BTCUSDT step size
    print("sized qty:", round(qty, 5))
    print(om.submit(OrderRequest("BTCUSDT", "BUY", round(qty, 5), stop_loss=59400)))
    print(om.submit(OrderRequest("BTCUSDT", "BUY", 0.5, stop_loss=59400)))
    print(om.submit(OrderRequest("BTCUSDT", "BUY", 0.01)))
