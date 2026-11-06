"""
Automatic Market Scanner Service
Continuously scans supported Indian indices and F&O stocks,
applies the centralized Fibonacci engine, evaluates near-target proximity,
and recommends actionable CE/PE strikes with real-time updates.
"""
import time
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime
from fib_engine import FibonacciEngine
from instrument_manager import InstrumentManager
from angel_service import AngelService

class ScannerService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ScannerService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.instrument_mgr = InstrumentManager()
        self.angel_service = AngelService()

        # Real-time state store: token -> market quote data
        self.market_store: Dict[str, Dict[str, Any]] = {}
        # Scanned strategy results: symbol -> scanner result item
        self.scan_results: Dict[str, Dict[str, Any]] = {}

        self.store_lock = threading.Lock()
        self.is_scanning = False
        self.proximity_threshold_pct: float = 0.1  # 0.1% proximity default
        self.auto_refresh_seconds: int = 5
        self.last_scan_time: Optional[str] = None

        # Register live tick callback with AngelService
        self.angel_service.register_tick_callback(self.on_market_tick)

        # Prepopulate market store with baseline values
        self._initialize_baseline_store()

        # Start periodic background scanner loop
        threading.Thread(target=self._scanner_loop, daemon=True).start()

    def _initialize_baseline_store(self):
        # Initial baseline reference quotes for key instruments so scanner is never empty
        baseline_prices = {
            "26000": {"symbol": "NIFTY", "name": "NIFTY", "ltp": 24150.0, "high": 24220.0, "low": 24080.0, "step": 50, "exch": 1},
            "26009": {"symbol": "BANKNIFTY", "name": "BANKNIFTY", "ltp": 51200.0, "high": 51450.0, "low": 50950.0, "step": 100, "exch": 1},
            "26037": {"symbol": "FINNIFTY", "name": "FINNIFTY", "ltp": 23800.0, "high": 23920.0, "low": 23690.0, "step": 50, "exch": 1},
            "26013": {"symbol": "MIDCPNIFTY", "name": "MIDCPNIFTY", "ltp": 12600.0, "high": 12680.0, "low": 12520.0, "step": 25, "exch": 1},
            "99919000": {"symbol": "SENSEX", "name": "SENSEX", "ltp": 79400.0, "high": 79650.0, "low": 79150.0, "step": 100, "exch": 3},
            "99919012": {"symbol": "BANKEX", "name": "BANKEX", "ltp": 58100.0, "high": 58350.0, "low": 57850.0, "step": 100, "exch": 3},
            "2885": {"symbol": "RELIANCE", "name": "RELIANCE", "ltp": 1320.0, "high": 1332.0, "low": 1312.0, "step": 20, "exch": 1},
            "11536": {"symbol": "TCS", "name": "TCS", "ltp": 4120.0, "high": 4150.0, "low": 4095.0, "step": 20, "exch": 1},
            "1594": {"symbol": "INFY", "name": "INFY", "ltp": 1840.0, "high": 1858.0, "low": 1828.0, "step": 10, "exch": 1},
            "3045": {"symbol": "SBIN", "name": "SBIN", "ltp": 820.0, "high": 828.0, "low": 814.0, "step": 10, "exch": 1},
            "1333": {"symbol": "HDFCBANK", "name": "HDFCBANK", "ltp": 1740.0, "high": 1755.0, "low": 1730.0, "step": 10, "exch": 1},
            "1660": {"symbol": "ICICIBANK", "name": "ICICIBANK", "ltp": 1260.0, "high": 1272.0, "low": 1251.0, "step": 10, "exch": 1}
        }
        with self.store_lock:
            for token, item in baseline_prices.items():
                self.market_store[token] = {
                    "token": token,
                    "symbol": item["symbol"],
                    "name": item["name"],
                    "ltp": item["ltp"],
                    "high": item["high"],
                    "low": item["low"],
                    "prev_close": item["ltp"],
                    "volume": 0,
                    "step": item["step"],
                    "exchange_type": item["exch"],
                    "last_updated": datetime.now().strftime("%H:%M:%S")
                }

    def on_market_tick(self, tick: Dict[str, Any]):
        """Receive live WebSocket tick and update market store & scan evaluation."""
        token = str(tick.get("token"))
        ltp = tick.get("ltp", 0.0)
        if not token or ltp <= 0:
            return

        with self.store_lock:
            info = self.market_store.get(token)
            if not info:
                # Lookup instrument details
                instr = self.instrument_mgr.get_token_info(token)
                sym = instr.get("symbol", token) if instr else token
                name = instr.get("name", sym) if instr else sym
                step = instr.get("step", 50) if instr else 50
                info = {
                    "token": token,
                    "symbol": sym,
                    "name": name,
                    "ltp": ltp,
                    "high": tick.get("high", ltp * 1.005),
                    "low": tick.get("low", ltp * 0.995),
                    "prev_close": tick.get("prev_close", ltp),
                    "volume": tick.get("volume", 0),
                    "step": step,
                    "exchange_type": tick.get("exchange_type", 1),
                    "last_updated": datetime.now().strftime("%H:%M:%S")
                }
                self.market_store[token] = info
            else:
                info["ltp"] = ltp
                if tick.get("high", 0) > 0:
                    info["high"] = tick["high"]
                if tick.get("low", 0) > 0:
                    info["low"] = tick["low"]
                if tick.get("prev_close", 0) > 0:
                    info["prev_close"] = tick["prev_close"]
                info["volume"] = tick.get("volume", info.get("volume", 0))
                info["last_updated"] = datetime.now().strftime("%H:%M:%S")

        # Evaluate strategy for this instrument immediately
        self._evaluate_instrument(info)

    def _evaluate_instrument(self, item: Dict[str, Any]):
        symbol = item.get("symbol", "")
        ltp = item.get("ltp", 0.0)
        high = item.get("high", ltp * 1.005)
        low = item.get("low", ltp * 0.995)
        step = item.get("step", 50.0)

        if ltp <= 0:
            return

        # Calculate Fibonacci setup
        eval_res = FibonacciEngine.evaluate_strategy(
            symbol=symbol,
            ltp=ltp,
            high=high,
            low=low,
            strike_step=step,
            proximity_threshold=ltp * (self.proximity_threshold_pct / 100.0)
        )

        # Match relevant option contract from Option Chain
        opt_chain = self.instrument_mgr.get_option_chain(symbol)
        expiry = opt_chain.get("selected_expiry")
        atm_strike = eval_res["atm_strike"]
        option_type = eval_res["option_type"]

        matching_option_token = None
        matching_option_symbol = None
        matching_option_ltp = 0.0

        for stk_data in opt_chain.get("strikes", []):
            if abs(stk_data["strike"] - atm_strike) < 0.1:
                opt_info = stk_data.get("ce" if option_type == "CE" else "pe")
                if opt_info:
                    matching_option_token = opt_info.get("token")
                    matching_option_symbol = opt_info.get("symbol")
                    # Check if we have live quote for option
                    with self.store_lock:
                        if matching_option_token in self.market_store:
                            matching_option_ltp = self.market_store[matching_option_token].get("ltp", 0.0)
                break

        # If live option quote is not yet available, estimate baseline option premium
        if matching_option_ltp <= 0:
            diff = max(high - low, ltp * 0.005)
            # Intrinsic / Time value approximation
            matching_option_ltp = round(max(diff * 0.15, ltp * 0.008), 2)

        change = round(ltp - item.get("prev_close", ltp), 2)
        change_pct = round((change / item["prev_close"] * 100.0), 2) if item.get("prev_close", 0) > 0 else 0.0

        scan_item = {
            "token": item.get("token"),
            "symbol": symbol,
            "name": item.get("name", symbol),
            "direction": eval_res["direction"],
            "option_type": option_type,
            "expiry": expiry or "Current",
            "strike": atm_strike,
            "option_token": matching_option_token,
            "option_symbol": matching_option_symbol or f"{symbol} {int(atm_strike)} {option_type}",
            "option_ltp": matching_option_ltp,
            "underlying_ltp": ltp,
            "high": high,
            "low": low,
            "change": change,
            "change_pct": change_pct,
            "entry": eval_res["entry"],
            "stop_loss": eval_res["stop_loss"],
            "target_1": eval_res["target_1"],
            "target_2": eval_res["target_2"],
            "target_3": eval_res["target_3"],
            "target_4": eval_res["target_4"],
            "status": eval_res["status"],
            "status_text": eval_res["status_text"],
            "status_color": eval_res["status_color"],
            "distance": eval_res["distance_entry"],
            "nearest_ray": eval_res["nearest_ray"],
            "action_label": eval_res["action_label"],
            "strategy_levels": eval_res["strategy_levels"],
            "last_updated": item.get("last_updated", datetime.now().strftime("%H:%M:%S"))
        }

        with self.store_lock:
            self.scan_results[symbol] = scan_item

    def _scanner_loop(self):
        """Periodic background scanner over all scannable instruments."""
        while True:
            try:
                scannable = self.instrument_mgr.get_all_scannable()
                tokens_to_subscribe = []

                for item in scannable:
                    tok = str(item["token"])
                    exch_type = 3 if item.get("exchange") == "BSE" else 1
                    tokens_to_subscribe.append({"token": tok, "exchange_type": exch_type})

                    with self.store_lock:
                        if tok not in self.market_store:
                            self.market_store[tok] = {
                                "token": tok,
                                "symbol": item["symbol"],
                                "name": item["name"],
                                "ltp": 0.0,
                                "high": 0.0,
                                "low": 0.0,
                                "prev_close": 0.0,
                                "volume": 0,
                                "step": item.get("step", 50),
                                "exchange_type": exch_type,
                                "last_updated": datetime.now().strftime("%H:%M:%S")
                            }
                        entry = dict(self.market_store[tok])

                    if entry["ltp"] > 0:
                        self._evaluate_instrument(entry)

                # Subscribe tokens via SmartWebSocketV2 if authenticated
                if self.angel_service.is_authenticated and tokens_to_subscribe:
                    # Batch subscribe the core tokens
                    self.angel_service.subscribe_tokens(tokens_to_subscribe[:50], mode=2)

                self.last_scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            except Exception as e:
                print(f"[ScannerService Error]: {e}")

            time.sleep(self.auto_refresh_seconds)

    def get_scanner_results(
        self,
        direction_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        option_filter: Optional[str] = None,
        search_query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve filtered scanner results."""
        with self.store_lock:
            items = list(self.scan_results.values())

        filtered = []
        for itm in items:
            if direction_filter and itm["direction"].upper() != direction_filter.upper():
                continue
            if option_filter and itm["option_type"].upper() != option_filter.upper():
                continue
            if status_filter:
                if status_filter == "NEAR_ENTRY" and itm["status"] != "NEAR_ENTRY":
                    continue
                elif status_filter == "NEAR_TARGET" and "TARGET" not in itm["status"]:
                    continue
                elif status_filter == "ACTIVE" and itm["status"] == "WAITING_FOR_ENTRY":
                    continue
            if search_query:
                q = search_query.strip().upper()
                if q not in itm["symbol"].upper() and q not in itm["name"].upper():
                    continue
            filtered.append(itm)

        # Sort by distance to entry (nearest opportunities first)
        return sorted(filtered, key=lambda x: (x["status"] == "WAITING_FOR_ENTRY", x["distance"]))

    def get_instrument_detail(self, token: str) -> Optional[Dict[str, Any]]:
        """Get full instrument market quote and strategy levels."""
        with self.store_lock:
            # Check market store by token
            quote = self.market_store.get(str(token))
            if quote and quote["ltp"] > 0:
                sym = quote.get("symbol")
                if sym in self.scan_results:
                    return self.scan_results[sym]

        # Lookup from instrument manager
        info = self.instrument_mgr.get_token_info(str(token))
        if info:
            sym = info["symbol"]
            with self.store_lock:
                if sym in self.scan_results:
                    return self.scan_results[sym]

        return None
