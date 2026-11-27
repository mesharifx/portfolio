"""Checks BinanceTestnet request building with a fake HTTP layer (no network)."""
import hashlib, hmac, os
from urllib.parse import urlparse, parse_qsl
os.environ["BINANCE_TESTNET_KEY"] = "k"; os.environ["BINANCE_TESTNET_SECRET"] = "s"
from trading_core_sample import *

class Resp:
    def __init__(s, data): s.data = data
    def raise_for_status(s): pass
    def json(s): return s.data

calls = []
class FakeSession:
    headers = {}
    def request(s, method, url, timeout):
        calls.append((method, url))
        if "/account" in url: return Resp({"balances": [{"asset": "USDT", "free": "10000.0"}]})
        if method == "DELETE": return Resp({"status": "CANCELED"})
        return Resp({"orderId": 42, "status": "NEW"})
    def get(s, url, params, timeout): return Resp({"price": "60000.00"})

b = BinanceTestnet(); b.http = FakeSession()
assert b.balance("USDT") == 10000.0 and b.balance("XYZ") == 0.0
assert b.last_price("BTCUSDT") == 60000.0
r = b.place_order(OrderRequest("BTCUSDT", "BUY", 0.00001, "STOP_LOSS_LIMIT", price=59000, stop_price=59100))
assert r.ok and r.order_id == "42"
m, url = calls[-1]; q = urlparse(url).query
p = dict(parse_qsl(q))
assert m == "POST" and p["quantity"] == "0.00001" and p["price"] == "59000" and p["stopPrice"] == "59100"
assert p["timeInForce"] == "GTC" and "e-" not in q and "None" not in q
unsigned, sig = q.rsplit("&signature=", 1)
assert sig == hmac.new(b"s", unsigned.encode(), hashlib.sha256).hexdigest()
assert b.cancel_order("BTCUSDT", "42").status == "CANCELED"
om = OrderManager(b, RiskManager(RiskConfig()))
assert not om.submit(OrderRequest("BTCUSDT", "BUY", 0.01, "LIMIT", stop_loss=59000)).ok
assert om.submit(OrderRequest("BTCUSDT", "BUY", 0.1, "LIMIT", price=59800, stop_loss=59200)).ok
print("BINANCE MOCK TESTS PASSED")
import requests as rq
class Bad:
    status_code = 400; text = '{"code":-1013,"msg":"Filter failure: LOT_SIZE"}'
class ErrSession(FakeSession):
    def request(s, method, url, timeout):
        e = rq.HTTPError("400"); e.response = Bad(); raise e
class NetSession(FakeSession):
    def request(s, method, url, timeout): raise rq.ConnectionError("timeout")
b.http = ErrSession()
r = b.place_order(OrderRequest("BTCUSDT","BUY",0.1)); assert not r.ok and "-1013" in r.reason
r = b.cancel_order("BTCUSDT","42"); assert not r.ok and "400" in r.reason
b.http = NetSession()
r = b.place_order(OrderRequest("BTCUSDT","BUY",0.1)); assert not r.ok and "network error" in r.reason
print("ERROR HANDLING TESTS PASSED")
