from trading_core_sample import *

ex = PaperExchange({"BTCUSDT": 60000.0}, usdt=10_000)
rm = RiskManager(RiskConfig())
om = OrderManager(ex, rm)

q = rm.size_position(10_000, 60000, 59400)
assert abs(q - 100/600) < 1e-9
assert om.submit(OrderRequest("BTCUSDT", "BUY", round(q, 6), stop_loss=59400)).ok
r = om.submit(OrderRequest("BTCUSDT", "BUY", 0.5, stop_loss=59400)); assert not r.ok and "exceeds" in r.reason
r = om.submit(OrderRequest("BTCUSDT", "BUY", 0.01)); assert not r.ok and "required" in r.reason
r = om.submit(OrderRequest("BTCUSDT", "BUY", 0.01, stop_loss=61000)); assert not r.ok and "wrong side" in r.reason
r = om.submit(OrderRequest("BTCUSDT", "SELL", 0.1, stop_loss=60600)); assert r.ok
lim = om.submit(OrderRequest("BTCUSDT", "BUY", 0.1, "LIMIT", price=59800, stop_loss=59200)); assert lim.status == "NEW"
assert ex.cancel_order("BTCUSDT", lim.order_id).status == "CANCELED"
rm.record_pnl(-300)
r = om.submit(OrderRequest("BTCUSDT", "BUY", 0.01, stop_loss=59400)); assert not r.ok and "daily" in r.reason
print("ALL TESTS PASSED")
# day rollover resets the counter and the day-start equity
from datetime import timedelta
rm.day = rm.day - timedelta(days=1)
r = om.submit(OrderRequest("BTCUSDT", "BUY", 0.01, stop_loss=59400)); assert r.ok and rm.realized_pnl_today == 0
# validation
for bad in [OrderRequest("BTCUSDT","HOLD",1,stop_loss=1), OrderRequest("BTCUSDT","BUY",0,stop_loss=1),
            OrderRequest("BTCUSDT","BUY",0.01,"STOP_LOSS_LIMIT",price=59000,stop_loss=58000),
            OrderRequest("BTCUSDT","BUY",0.01,"OCO",price=1,stop_loss=1)]:
    assert om.submit(bad).status == "REJECTED"
# daily limit measured from day-start equity, not current balance
rm2 = RiskManager(RiskConfig()); ex2 = PaperExchange({"BTCUSDT":60000.0}, 10_000); om2 = OrderManager(ex2, rm2)
assert om2.submit(OrderRequest("BTCUSDT","BUY",0.01,stop_loss=59400)).ok
rm2.record_pnl(-299); ex2.balances["USDT"] = 9_701
assert om2.submit(OrderRequest("BTCUSDT","BUY",0.01,stop_loss=59400)).ok
rm2.record_pnl(-1); assert not om2.submit(OrderRequest("BTCUSDT","BUY",0.01,stop_loss=59400)).ok
print("EXTRA TESTS PASSED")
