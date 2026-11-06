"""
Instrument Master & Market Discovery Manager
Downloads and parses Angel One Scrip Master JSON.
Dynamically discovers indices, F&O stocks, option chains, expiries, and strike prices.
"""
import os
import json
import time
import threading
from typing import Dict, List, Any, Optional
import requests
from datetime import datetime

SCRIP_MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_FILE = os.path.join(CACHE_DIR, "scrip_master.json")
INDEX_CACHE_FILE = os.path.join(CACHE_DIR, "indexed_instruments.json")

# Verified core Indian indices
CORE_INDICES = [
    {"token": "26000", "symbol": "NIFTY", "name": "NIFTY", "display": "NIFTY 50", "exchange": "NSE", "step": 50, "is_index": True},
    {"token": "26009", "symbol": "BANKNIFTY", "name": "BANKNIFTY", "display": "BANK NIFTY", "exchange": "NSE", "step": 100, "is_index": True},
    {"token": "26037", "symbol": "FINNIFTY", "name": "FINNIFTY", "display": "FIN NIFTY", "exchange": "NSE", "step": 50, "is_index": True},
    {"token": "26013", "symbol": "MIDCPNIFTY", "name": "MIDCPNIFTY", "display": "MIDCAP NIFTY", "exchange": "NSE", "step": 25, "is_index": True},
    {"token": "26014", "symbol": "NIFTYNXT50", "name": "NIFTYNXT50", "display": "NIFTY NEXT 50", "exchange": "NSE", "step": 100, "is_index": True},
    {"token": "99919000", "symbol": "SENSEX", "name": "SENSEX", "display": "SENSEX", "exchange": "BSE", "step": 100, "is_index": True},
    {"token": "99919012", "symbol": "BANKEX", "name": "BANKEX", "display": "BANKEX", "exchange": "BSE", "step": 100, "is_index": True}
]

# Popular fallback F&O stocks for immediate initialization
DEFAULT_FO_STOCKS = [
    {"token": "2885", "symbol": "RELIANCE", "name": "RELIANCE", "exchange": "NSE", "step": 20, "is_index": False},
    {"token": "11536", "symbol": "TCS", "name": "TCS", "exchange": "NSE", "step": 20, "is_index": False},
    {"token": "1594", "symbol": "INFY", "name": "INFY", "exchange": "NSE", "step": 10, "is_index": False},
    {"token": "3045", "symbol": "SBIN", "name": "SBIN", "exchange": "NSE", "step": 10, "is_index": False},
    {"token": "1333", "symbol": "HDFCBANK", "name": "HDFCBANK", "exchange": "NSE", "step": 10, "is_index": False},
    {"token": "1660", "symbol": "ICICIBANK", "name": "ICICIBANK", "exchange": "NSE", "step": 10, "is_index": False},
    {"token": "3456", "symbol": "TATAMOTORS", "name": "TATAMOTORS", "exchange": "NSE", "step": 10, "is_index": False},
    {"token": "3499", "symbol": "TATASTEEL", "name": "TATASTEEL", "exchange": "NSE", "step": 2, "is_index": False},
    {"token": "11723", "symbol": "BAJFINANCE", "name": "BAJFINANCE", "exchange": "NSE", "step": 50, "is_index": False},
    {"token": "317", "symbol": "BAJAJFINSV", "name": "BAJAJFINSV", "exchange": "NSE", "step": 20, "is_index": False},
    {"token": "5900", "symbol": "AXISBANK", "name": "AXISBANK", "exchange": "NSE", "step": 10, "is_index": False},
    {"token": "1922", "symbol": "KOTAKBANK", "name": "KOTAKBANK", "exchange": "NSE", "step": 10, "is_index": False},
    {"token": "1394", "symbol": "LT", "name": "LT", "exchange": "NSE", "step": 20, "is_index": False},
    {"token": "10940", "symbol": "BHARTIARTL", "name": "BHARTIARTL", "exchange": "NSE", "step": 10, "is_index": False},
    {"token": "526", "symbol": "ITC", "name": "ITC", "exchange": "NSE", "step": 5, "is_index": False}
]

class InstrumentManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(InstrumentManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.indices: List[Dict[str, Any]] = list(CORE_INDICES)
        self.fo_stocks: List[Dict[str, Any]] = list(DEFAULT_FO_STOCKS)
        self.token_lookup: Dict[str, Dict[str, Any]] = {}
        self.option_contracts: Dict[str, List[Dict[str, Any]]] = {}  # symbol -> list of option contracts
        self.is_master_loaded = False
        self.is_downloading = False
        self.last_sync_time: Optional[str] = None

        self._build_initial_lookup()
        # Start background load or update
        threading.Thread(target=self.initialize_master_data, daemon=True).start()

    def _build_initial_lookup(self):
        for item in self.indices + self.fo_stocks:
            self.token_lookup[str(item["token"])] = item

    def get_token_info(self, token: str) -> Optional[Dict[str, Any]]:
        return self.token_lookup.get(str(token))

    def get_supported_indices(self) -> List[Dict[str, Any]]:
        return self.indices

    def get_fo_stocks(self) -> List[Dict[str, Any]]:
        return self.fo_stocks

    def get_all_scannable(self) -> List[Dict[str, Any]]:
        return self.indices + self.fo_stocks

    def initialize_master_data(self):
        """Load from cache if fresh (within 24h) or download from Angel One."""
        os.makedirs(CACHE_DIR, exist_ok=True)
        should_download = True

        if os.path.exists(INDEX_CACHE_FILE):
            try:
                mtime = os.path.getmtime(INDEX_CACHE_FILE)
                if (time.time() - mtime) < 86400:  # Fresh within 24h
                    print("[InstrumentManager] Loading indexed master data from local cache...")
                    with open(INDEX_CACHE_FILE, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                        self.fo_stocks = cache_data.get("fo_stocks", self.fo_stocks)
                        self.option_contracts = cache_data.get("option_contracts", {})
                        for item in self.fo_stocks:
                            self.token_lookup[str(item["token"])] = item
                        self.is_master_loaded = True
                        self.last_sync_time = cache_data.get("sync_time", datetime.now().isoformat())
                        print(f"[InstrumentManager] Loaded {len(self.fo_stocks)} F&O stocks and option chains from cache.")
                        should_download = False
            except Exception as e:
                print(f"[InstrumentManager] Cache load warning: {e}")

        if should_download:
            self.download_and_index_master()

    def download_and_index_master(self):
        if self.is_downloading:
            return
        self.is_downloading = True
        print(f"[InstrumentManager] Downloading official Scrip Master from {SCRIP_MASTER_URL}...")

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            resp = requests.get(SCRIP_MASTER_URL, headers=headers, timeout=45)
            if resp.status_code != 200:
                print(f"[InstrumentManager] Download failed with status {resp.status_code}")
                self.is_downloading = False
                return

            raw_instruments = resp.json()
            print(f"[InstrumentManager] Downloaded {len(raw_instruments)} instruments. Indexing...")

            fo_symbols = set()
            options_by_symbol: Dict[str, List[Dict[str, Any]]] = {}

            # First pass: Identify all NFO F&O instruments and group options
            for item in raw_instruments:
                exch = item.get("exch_seg")
                itype = item.get("instrumenttype")
                name = item.get("name", "").strip()

                if exch == "NFO":
                    if itype in ["OPTIDX", "OPTSTK"]:
                        fo_symbols.add(name)
                        if name not in options_by_symbol:
                            options_by_symbol[name] = []
                        
                        try:
                            strike_val = float(item.get("strike", 0)) / 100.0 if float(item.get("strike", 0)) > 10000 else float(item.get("strike", 0))
                        except Exception:
                            strike_val = 0.0

                        options_by_symbol[name].append({
                            "token": item.get("token"),
                            "symbol": item.get("symbol"),
                            "name": name,
                            "expiry": item.get("expiry"),
                            "strike": strike_val,
                            "lotsize": int(item.get("lotsize", 1)),
                            "instrumenttype": itype,
                            "tick_size": float(item.get("tick_size", 5.0)) / 100.0,
                            "option_type": "CE" if item.get("symbol", "").endswith("CE") else ("PE" if item.get("symbol", "").endswith("PE") else "")
                        })

            # Second pass: Match cash equity tokens for F&O stocks
            discovered_stocks = []
            for item in raw_instruments:
                exch = item.get("exch_seg")
                sym = item.get("symbol", "")
                name = item.get("name", "").strip()

                if exch == "NSE" and sym.endswith("-EQ") and name in fo_symbols:
                    step = 10
                    # Estimate strike step from available options
                    opts = options_by_symbol.get(name, [])
                    if len(opts) >= 2:
                        strikes = sorted(list(set(o["strike"] for o in opts if o["strike"] > 0)))
                        if len(strikes) >= 2:
                            diffs = [strikes[i+1] - strikes[i] for i in range(min(5, len(strikes)-1))]
                            step = min(diffs) if diffs else 10

                    stock_entry = {
                        "token": item.get("token"),
                        "symbol": name,
                        "tradingsymbol": sym,
                        "name": name,
                        "exchange": "NSE",
                        "step": step,
                        "is_index": False
                    }
                    discovered_stocks.append(stock_entry)
                    self.token_lookup[str(item.get("token"))] = stock_entry

            if discovered_stocks:
                discovered_stocks.sort(key=lambda x: x["symbol"])
                self.fo_stocks = discovered_stocks

            self.option_contracts = options_by_symbol
            self.is_master_loaded = True
            self.last_sync_time = datetime.now().isoformat()

            # Save indexed data
            try:
                with open(INDEX_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "sync_time": self.last_sync_time,
                        "fo_stocks": self.fo_stocks,
                        "option_contracts": self.option_contracts
                    }, f)
                print(f"[InstrumentManager] Successfully indexed {len(self.fo_stocks)} F&O stocks & {sum(len(v) for v in self.option_contracts.values())} option contracts.")
            except Exception as e:
                print(f"[InstrumentManager] Failed to cache indexed file: {e}")

        except Exception as err:
            print(f"[InstrumentManager] Error during Scrip Master processing: {err}")
        finally:
            self.is_downloading = False

    def get_option_chain(self, symbol: str, expiry: Optional[str] = None) -> Dict[str, Any]:
        """
        Build full option chain for a given symbol and expiry:
        - List of available expiries
        - ATM strike identification
        - Strikes table with Call (CE) and Put (PE) metadata and contracts
        """
        symbol = symbol.upper()
        raw_options = self.option_contracts.get(symbol, [])

        if not raw_options:
            return {"symbol": symbol, "expiries": [], "selected_expiry": None, "strikes": []}

        # Collect unique expiries and sort them chronologically
        def parse_exp(exp_str):
            try:
                return datetime.strptime(exp_str.strip(), "%d%b%Y")
            except Exception:
                try:
                    return datetime.strptime(exp_str.strip(), "%d-%b-%Y")
                except Exception:
                    return datetime.max

        unique_expiries = list(set(o["expiry"] for o in raw_options if o.get("expiry")))
        sorted_expiries = sorted(unique_expiries, key=parse_exp)

        if not expiry or expiry not in sorted_expiries:
            expiry = sorted_expiries[0] if sorted_expiries else None

        if not expiry:
            return {"symbol": symbol, "expiries": [], "selected_expiry": None, "strikes": []}

        # Filter options for the selected expiry
        expiry_options = [o for o in raw_options if o.get("expiry") == expiry]

        # Group by strike
        strikes_map: Dict[float, Dict[str, Any]] = {}
        for opt in expiry_options:
            stk = opt["strike"]
            if stk not in strikes_map:
                strikes_map[stk] = {
                    "strike": stk,
                    "ce": None,
                    "pe": None
                }
            if opt["option_type"] == "CE":
                strikes_map[stk]["ce"] = opt
                self.token_lookup[str(opt["token"])] = opt
            elif opt["option_type"] == "PE":
                strikes_map[stk]["pe"] = opt
                self.token_lookup[str(opt["token"])] = opt

        sorted_strikes = [strikes_map[k] for k in sorted(strikes_map.keys())]

        return {
            "symbol": symbol,
            "expiries": sorted_expiries,
            "selected_expiry": expiry,
            "strikes": sorted_strikes
        }
