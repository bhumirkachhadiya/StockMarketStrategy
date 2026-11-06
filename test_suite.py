"""
Comprehensive Automated Test Suite for Fib-Precision Indian Stock Market Platform
Tests:
- Fibonacci Strategy Engine calculations and 6 exact price levels
- Option contract exact strategy price levels
- Proximity and near-target detection
- Instrument discovery and option chain mapping
- Angel One authentication validation and TOTP generation
- Indian market session detection (Asia/Kolkata)
- Multi-timeframe historical/intraday candles (1m, 3m, 5m, 15m, 30m, 1h, 1D)
- Flask REST APIs, contract levels, health checks, and database settings
"""
import unittest
import json
import pyotp
from fib_engine import FibonacciEngine
from instrument_manager import InstrumentManager
from angel_service import AngelService
from database import Database
from app import app

class TestFibonacciEngine(unittest.TestCase):
    def test_fib_rays_calculation(self):
        high = 22500.0
        low = 22000.0
        levels = FibonacciEngine.calculate_fib_levels(high, low)
        self.assertEqual(len(levels), 8)
        diff = 500.0
        expected_fib_a_236 = round(high - (diff * 0.236), 2)
        found = any(abs(l["price"] - expected_fib_a_236) < 0.01 for l in levels)
        self.assertTrue(found, f"Expected Fib A (0.236) at {expected_fib_a_236}")

    def test_six_strategy_levels_with_exact_metrics(self):
        res = FibonacciEngine.evaluate_strategy("NIFTY", 22450.0, 22520.0, 22380.0, strike_step=50.0)
        self.assertIn("strategy_levels", res)
        strat_levels = res["strategy_levels"]
        self.assertEqual(len(strat_levels), 6)
        codes = [lvl["code"] for lvl in strat_levels]
        self.assertListEqual(codes, ["SL", "ENTRY", "T1", "T2", "T3", "T4"])

        # Check that each level has exact price, distance in Rs, diff %, and hit status
        for lvl in strat_levels:
            self.assertIn("price", lvl)
            self.assertIn("distance", lvl)
            self.assertIn("distance_pct", lvl)
            self.assertIn("hit_status", lvl)
            self.assertIn("is_hit", lvl)
            self.assertTrue(lvl["price"] > 0)

        # Check PnL metrics
        self.assertIn("pnl_points", res)
        self.assertIn("pnl_pct", res)
        self.assertIn("dist_to_next_target", res)
        self.assertIn("dist_to_sl", res)

    def test_option_contract_strategy(self):
        # Test option contract individual pricing (e.g. ₹100 CE)
        res = FibonacciEngine.evaluate_option_contract_strategy("NIFTY24200CE", 100.0, 115.0, 85.0, "CE")
        self.assertEqual(len(res["strategy_levels"]), 6)
        self.assertEqual(res["entry"], 100.0)
        self.assertTrue(res["stop_loss"] < 100.0)
        self.assertTrue(res["target_1"] > 100.0)
        self.assertTrue(res["target_2"] > res["target_1"])

    def test_atm_strike_calculation(self):
        self.assertEqual(FibonacciEngine.get_atm_strike(24162.0, 50.0), 24150.0)
        self.assertEqual(FibonacciEngine.get_atm_strike(24185.0, 50.0), 24200.0)
        self.assertEqual(FibonacciEngine.get_atm_strike(51240.0, 100.0), 51200.0)
        self.assertEqual(FibonacciEngine.get_atm_strike(1324.0, 20.0), 1320.0)

    def test_near_entry_proximity(self):
        high = 22500.0
        low = 22000.0
        res = FibonacciEngine.evaluate_strategy("TEST", 22118.5, high, low, proximity_threshold=5.0)
        self.assertIn(res["status"], ["NEAR_ENTRY", "ENTRY_TRIGGERED", "WAITING_FOR_ENTRY"])

class TestInstrumentManager(unittest.TestCase):
    def setUp(self):
        self.mgr = InstrumentManager()

    def test_supported_indices(self):
        indices = self.mgr.get_supported_indices()
        symbols = [x["symbol"] for x in indices]
        self.assertIn("NIFTY", symbols)
        self.assertIn("BANKNIFTY", symbols)
        self.assertIn("FINNIFTY", symbols)
        self.assertIn("SENSEX", symbols)
        self.assertIn("BANKEX", symbols)

    def test_fo_stocks(self):
        stocks = self.mgr.get_fo_stocks()
        self.assertTrue(len(stocks) >= 12)
        symbols = [x["symbol"] for x in stocks]
        self.assertIn("RELIANCE", symbols)
        self.assertIn("TCS", symbols)
        self.assertIn("INFY", symbols)

    def test_option_chain_structure(self):
        chain = self.mgr.get_option_chain("NIFTY")
        self.assertIn("symbol", chain)
        self.assertIn("expiries", chain)
        self.assertIn("strikes", chain)

class TestAngelService(unittest.TestCase):
    def setUp(self):
        self.svc = AngelService()

    def test_totp_generation(self):
        secret = pyotp.random_base32()
        code = self.svc.generate_totp_code(secret)
        self.assertIsNotNone(code)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_market_status_detection(self):
        status = self.svc.get_market_status()
        self.assertIn("is_open", status)
        self.assertIn("status_code", status)
        self.assertIn("status_label", status)
        self.assertIn("ist_time", status)
        self.assertIn("IST", status["ist_time"])

    def test_auth_validation(self):
        res = self.svc.authenticate(client_id="TEST", api_key="KEY", pin="1234", totp_code="")
        self.assertFalse(res["status"])
        self.assertIn("TOTP", res["message"])

class TestDatabase(unittest.TestCase):
    def test_settings_storage(self):
        db = Database()
        db.set_setting("test_key", {"threshold": 0.25})
        val = db.get_setting("test_key")
        self.assertEqual(val["threshold"], 0.25)

class TestFlaskEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index_route(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"FIB-PRECISION", response.data)

    def test_health_endpoints(self):
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["status"], "healthy")

        res_api = self.client.get('/api/health')
        self.assertEqual(res_api.status_code, 200)

    def test_market_status_endpoint(self):
        response = self.client.get('/api/market-status')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["status"])
        self.assertIn("status_code", data["data"])

    def test_contract_levels_endpoint(self):
        # Test Underlying levels
        res1 = self.client.get('/api/contract-levels?token=26000&symbol=NIFTY&ltp=24150')
        self.assertEqual(res1.status_code, 200)
        d1 = json.loads(res1.data)
        self.assertTrue(d1["status"])
        self.assertEqual(len(d1["data"]["strategy_levels"]), 6)

        # Test Option Contract levels
        res2 = self.client.get('/api/contract-levels?token=35262&symbol=NIFTY24200CE&ltp=120.0&is_option=true')
        self.assertEqual(res2.status_code, 200)
        d2 = json.loads(res2.data)
        self.assertTrue(d2["status"])
        self.assertEqual(len(d2["data"]["strategy_levels"]), 6)
        self.assertEqual(d2["data"]["entry"], 120.0)

    def test_multi_timeframe_candles(self):
        for tf in ["1m", "3m", "5m", "15m", "30m", "1h", "1D"]:
            res = self.client.get(f'/api/candles?token=26000&exchange=NSE&interval={tf}')
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data)
            self.assertTrue(data["status"])
            self.assertTrue(len(data["candles"]) > 0)

    def test_option_chain_endpoint(self):
        response = self.client.get('/api/option-chain?symbol=NIFTY')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["status"])

    def test_scanner_endpoint(self):
        response = self.client.get('/api/scanner')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["status"])

if __name__ == '__main__':
    unittest.main()
