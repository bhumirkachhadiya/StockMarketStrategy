"""
Angel One SmartAPI Integration Service
Manages authentication, session tokens, REST API calls, historical candle retrieval,
and real-time SmartWebSocketV2 streaming with automatic reconnection,
market hours detection (Asia/Kolkata), and fallback REST quote polling.
"""
import os
import json
import time
import logging
import threading
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timezone, timedelta
import pyotp
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

logger = logging.getLogger("AngelService")
logger.setLevel(logging.INFO)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
# Indian Standard Time (IST) offset is UTC+05:30
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

class AngelService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AngelService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.api_key: str = os.environ.get("ANGEL_API_KEY", "MRx8rHZh")
        self.client_id: str = os.environ.get("ANGEL_CLIENT_ID", "AAAA492357")
        self.pin: str = os.environ.get("ANGEL_PIN", "6405")
        self.totp_secret: str = os.environ.get("ANGEL_TOTP_SECRET", "")

        self._load_saved_config()

        self.smart_connect: Optional[SmartConnect] = None
        self.smart_ws: Optional[SmartWebSocketV2] = None

        self.jwt_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.feed_token: Optional[str] = None
        self.user_profile: Optional[Dict[str, Any]] = None

        self.is_authenticated: bool = False
        self.is_ws_connected: bool = False
        self.last_auth_time: Optional[float] = None
        self.last_tick_time: Optional[float] = None
        self.auth_error_message: Optional[str] = None

        # Callbacks registered for live market ticks
        self.tick_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        # Active subscription tokens: token -> exchange_type
        self.active_subscriptions: Dict[str, int] = {}
        self.ws_lock = threading.Lock()

        # Start background polling worker for REST quotes when websocket is quiet or market closed
        threading.Thread(target=self._background_quote_poller, daemon=True).start()

    def _load_saved_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.api_key = cfg.get("api_key", self.api_key)
                    self.client_id = cfg.get("client_id", self.client_id)
                    self.pin = cfg.get("pin", self.pin)
                    self.totp_secret = cfg.get("totp_secret", self.totp_secret)
            except Exception as e:
                logger.warning(f"Failed to read config file: {e}")

    def save_config(self, api_key: str, client_id: str, pin: str, totp_secret: str = ""):
        self.api_key = api_key.strip()
        self.client_id = client_id.strip()
        self.pin = pin.strip()
        self.totp_secret = totp_secret.strip()
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "api_key": self.api_key,
                    "client_id": self.client_id,
                    "pin": self.pin,
                    "totp_secret": self.totp_secret
                }, f)
        except Exception as e:
            logger.error(f"Error saving config file: {e}")

    def get_market_status(self) -> Dict[str, Any]:
        """
        Evaluate current Indian Stock Market status according to Asia/Kolkata timezone:
        - Regular trading: Monday-Friday 09:15 to 15:30 IST
        - Pre-market: Monday-Friday 09:00 to 09:15 IST
        - Post-market: Monday-Friday 15:30 to 16:00 IST
        - Market closed: Evenings, nights, and weekends
        """
        now_ist = datetime.now(IST_OFFSET)
        weekday = now_ist.weekday()  # 0=Monday, 6=Sunday
        t = now_ist.time()

        t_pre = datetime.strptime("09:00", "%H:%M").time()
        t_open = datetime.strptime("09:15", "%H:%M").time()
        t_close = datetime.strptime("15:30", "%H:%M").time()
        t_post = datetime.strptime("16:00", "%H:%M").time()

        is_weekend = weekday >= 5
        is_open = False
        status_code = "MARKET_CLOSED"
        status_label = "Market Closed"
        reason = "Trading hours: 09:15 to 15:30 IST (Mon-Fri)"

        if is_weekend:
            reason = "Market closed for Weekend (Saturday/Sunday)"
        else:
            if t_open <= t <= t_close:
                is_open = True
                status_code = "LIVE"
                status_label = "Market Open (LIVE)"
                reason = "Regular trading session"
            elif t_pre <= t < t_open:
                status_code = "PRE_MARKET"
                status_label = "Pre-Market Session"
                reason = "Pre-market opening orders"
            elif t_close < t <= t_post:
                status_code = "POST_MARKET"
                status_label = "Post-Market Session"
                reason = "Post-market closing session"

        # Determine stream health status
        now_ts = time.time()
        if not self.is_authenticated:
            stream_status = "DISCONNECTED"
        elif self.is_ws_connected and self.last_tick_time and (now_ts - self.last_tick_time < 30):
            stream_status = "LIVE"
        elif self.is_ws_connected:
            stream_status = "IDLE" if not is_open else "DELAYED"
        else:
            stream_status = "REST_ACTIVE"

        return {
            "is_open": is_open,
            "status_code": status_code,
            "status_label": status_label,
            "reason": reason,
            "stream_status": stream_status,
            "ist_time": now_ist.strftime("%d-%b-%Y %H:%M:%S IST"),
            "is_weekend": is_weekend,
            "is_ws_connected": self.is_ws_connected,
            "is_authenticated": self.is_authenticated
        }

    def register_tick_callback(self, cb: Callable[[Dict[str, Any]], None]):
        with self.ws_lock:
            if cb not in self.tick_callbacks:
                self.tick_callbacks.append(cb)

    def generate_totp_code(self, secret: Optional[str] = None) -> Optional[str]:
        sec = secret or self.totp_secret
        if not sec:
            return None
        try:
            totp = pyotp.TOTP(sec.strip().replace(" ", "").upper())
            return totp.now()
        except Exception as e:
            logger.error(f"Error generating TOTP from secret: {e}")
            return None

    def authenticate(
        self,
        client_id: Optional[str] = None,
        api_key: Optional[str] = None,
        pin: Optional[str] = None,
        totp_code: Optional[str] = None,
        totp_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authenticate with Angel One SmartAPI using client credentials and TOTP.
        """
        cid = (client_id or self.client_id or "").strip()
        key = (api_key or self.api_key or "").strip()
        p = (pin or self.pin or "").strip()
        t_sec = (totp_secret or self.totp_secret or "").strip()
        code = (totp_code or "").strip()

        if not cid:
            return {"status": False, "message": "Client ID is required."}
        if not key:
            return {"status": False, "message": "API Key is required."}
        if not p:
            return {"status": False, "message": "PIN is required."}

        # Resolve TOTP code
        if not code and t_sec:
            code = self.generate_totp_code(t_sec)

        if not code or len(code) != 6 or not code.isdigit():
            return {"status": False, "message": "Valid 6-digit TOTP code is required."}

        logger.info(f"Initiating authentication for client: {cid}")

        try:
            sc = SmartConnect(api_key=key)
            session_data = sc.generateSession(cid, p, code)

            if not session_data or not session_data.get("status"):
                err_msg = session_data.get("message", "Authentication rejected by Angel One.") if isinstance(session_data, dict) else str(session_data)
                self.auth_error_message = err_msg
                self.is_authenticated = False
                logger.error(f"Authentication failed: {err_msg}")
                return {"status": False, "message": err_msg, "error_details": session_data}

            data = session_data.get("data", {})
            jwt = data.get("jwtToken", "")
            feed = data.get("feedToken", "")
            refresh = data.get("refreshToken", "")

            raw_jwt = jwt.replace("Bearer ", "").strip()

            self.smart_connect = sc
            self.jwt_token = raw_jwt
            self.feed_token = feed
            self.refresh_token = refresh
            self.user_profile = data
            self.is_authenticated = True
            self.last_auth_time = time.time()
            self.auth_error_message = None

            # Update working credentials
            self.client_id = cid
            self.api_key = key
            self.pin = p
            if t_sec:
                self.totp_secret = t_sec
            self.save_config(cid, key, p, t_sec)

            logger.info("Angel One authentication successful! Initializing WebSocket stream...")

            # Initialize and start WebSocket stream in background thread
            self.start_websocket()

            return {
                "status": True,
                "message": "Authentication successful!",
                "client_id": cid,
                "user_name": data.get("name", cid),
                "feed_token_available": bool(feed)
            }

        except Exception as ex:
            logger.exception("Unexpected error during authentication")
            self.auth_error_message = str(ex)
            self.is_authenticated = False
            return {"status": False, "message": f"Server error during authentication: {str(ex)}"}

    def logout(self) -> Dict[str, Any]:
        """Disconnect WebSocket and clear authenticated session."""
        try:
            if self.smart_ws:
                self.smart_ws.close_connection()
                self.smart_ws = None
        except Exception as e:
            logger.warning(f"Error closing websocket: {e}")

        self.smart_connect = None
        self.jwt_token = None
        self.feed_token = None
        self.refresh_token = None
        self.is_authenticated = False
        self.is_ws_connected = False
        self.active_subscriptions.clear()
        return {"status": True, "message": "Logged out successfully."}

    def start_websocket(self):
        """Establish SmartWebSocketV2 connection with correct parameter order and callbacks."""
        if not self.is_authenticated or not self.jwt_token or not self.feed_token:
            logger.warning("Cannot start WebSocket: Not authenticated or missing tokens.")
            return

        try:
            if self.smart_ws:
                try:
                    self.smart_ws.close_connection()
                except Exception:
                    pass
                self.smart_ws = None

            auth_header = f"Bearer {self.jwt_token}" if not self.jwt_token.startswith("Bearer ") else self.jwt_token
            sws = SmartWebSocketV2(
                auth_token=auth_header,
                api_key=self.api_key,
                client_code=self.client_id,
                feed_token=self.feed_token,
                max_retry_attempt=15,
                retry_delay=5
            )

            def on_open(wsapp):
                logger.info("[SmartWebSocket] Stream connected successfully!")
                self.is_ws_connected = True
                self._resubscribe_all()

            def on_data(wsapp, message):
                self.last_tick_time = time.time()
                if isinstance(message, dict):
                    self._dispatch_tick(message)

            def on_error(wsapp, error):
                logger.error(f"[SmartWebSocket Error]: {error}")
                self.is_ws_connected = False

            def on_close(wsapp):
                logger.info("[SmartWebSocket] Stream closed.")
                self.is_ws_connected = False

            sws.on_open = on_open
            sws.on_data = on_data
            sws.on_error = on_error
            sws.on_close = on_close

            self.smart_ws = sws
            t = threading.Thread(target=sws.connect, daemon=True)
            t.start()

        except Exception as e:
            logger.error(f"Failed to start SmartWebSocketV2: {e}")

    def _dispatch_tick(self, message: Dict[str, Any]):
        """Format tick data and dispatch to registered callbacks."""
        try:
            token = str(message.get("token", ""))
            ltp_raw = message.get("last_traded_price", 0)
            ltp = (ltp_raw / 100.0) if ltp_raw else 0.0

            high_raw = message.get("high_price_of_the_day", 0)
            low_raw = message.get("low_price_of_the_day", 0)
            open_raw = message.get("open_price_of_the_day", 0)
            close_raw = message.get("closed_price", 0)
            volume = message.get("volume_trade_for_the_day", 0)

            high = (high_raw / 100.0) if high_raw else (ltp * 1.008 if ltp else 0)
            low = (low_raw / 100.0) if low_raw else (ltp * 0.992 if ltp else 0)
            open_p = (open_raw / 100.0) if open_raw else ltp
            prev_close = (close_raw / 100.0) if close_raw else ltp

            formatted_tick = {
                "token": token,
                "exchange_type": message.get("exchange_type", 1),
                "ltp": ltp,
                "high": high,
                "low": low,
                "open": open_p,
                "prev_close": prev_close,
                "volume": volume,
                "sequence": message.get("sequence_number", 0),
                "timestamp": message.get("exchange_timestamp", int(time.time() * 1000))
            }

            with self.ws_lock:
                callbacks = list(self.tick_callbacks)

            for cb in callbacks:
                try:
                    cb(formatted_tick)
                except Exception as cb_err:
                    logger.warning(f"Error in tick callback: {cb_err}")

        except Exception as e:
            logger.error(f"Error formatting tick: {e}")

    def subscribe_tokens(self, tokens_with_exchange: List[Dict[str, Any]], mode: int = 2):
        if not tokens_with_exchange:
            return

        with self.ws_lock:
            for item in tokens_with_exchange:
                tok = str(item["token"])
                exch = int(item.get("exchange_type", 1))
                self.active_subscriptions[tok] = exch

        if not self.smart_ws or not self.is_ws_connected:
            return

        grouped: Dict[int, List[str]] = {}
        for item in tokens_with_exchange:
            exch = int(item.get("exchange_type", 1))
            tok = str(item["token"])
            if exch not in grouped:
                grouped[exch] = []
            grouped[exch].append(tok)

        token_list = [{"exchangeType": exch, "tokens": toks} for exch, toks in grouped.items()]
        try:
            self.smart_ws.subscribe(correlation_id="app_stream", mode=mode, token_list=token_list)
        except Exception as e:
            logger.error(f"Subscription error: {e}")

    def _resubscribe_all(self):
        with self.ws_lock:
            if not self.active_subscriptions:
                return
            items = [{"token": tok, "exchange_type": exch} for tok, exch in self.active_subscriptions.items()]
        self.subscribe_tokens(items, mode=2)

    def get_ltp_rest(self, exchange: str, tradingsymbol: str, symboltoken: str) -> Optional[float]:
        """Fetch real-time LTP via REST API quote endpoint."""
        if not self.smart_connect or not self.is_authenticated:
            return None
        try:
            resp = self.smart_connect.ltpData(exchange, tradingsymbol, symboltoken)
            if resp and resp.get("status") and "data" in resp:
                return float(resp["data"].get("ltp", 0))
        except Exception as e:
            logger.warning(f"REST LTP fetch failed for {tradingsymbol}: {e}")
        return None

    def get_historical_candles(
        self,
        exchange: str,
        symboltoken: str,
        interval: str = "ONE_MINUTE",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical candle data using Angel One getCandleData.
        Supports intervals: ONE_MINUTE, THREE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE,
        THIRTY_MINUTE, ONE_HOUR, ONE_DAY.
        """
        # Supported SmartAPI intervals mapping
        api_interval_map = {
            "1m": "ONE_MINUTE",
            "ONE_MINUTE": "ONE_MINUTE",
            "3m": "THREE_MINUTE",
            "THREE_MINUTE": "THREE_MINUTE",
            "5m": "FIVE_MINUTE",
            "FIVE_MINUTE": "FIVE_MINUTE",
            "15m": "FIFTEEN_MINUTE",
            "FIFTEEN_MINUTE": "FIFTEEN_MINUTE",
            "30m": "THIRTY_MINUTE",
            "THIRTY_MINUTE": "THIRTY_MINUTE",
            "1h": "ONE_HOUR",
            "ONE_HOUR": "ONE_HOUR",
            "1D": "ONE_DAY",
            "ONE_DAY": "ONE_DAY"
        }
        mapped_interval = api_interval_map.get(interval, "ONE_MINUTE")

        if self.smart_connect and self.is_authenticated:
            try:
                now = datetime.now()
                if not from_date:
                    if mapped_interval == "ONE_DAY":
                        from_date = (now - timedelta(days=90)).strftime("%Y-%m-%d 09:15")
                    else:
                        from_date = (now - timedelta(days=5)).strftime("%Y-%m-%d 09:15")
                if not to_date:
                    to_date = now.strftime("%Y-%m-%d 15:30")

                params = {
                    "exchange": exchange,
                    "symboltoken": symboltoken,
                    "interval": mapped_interval,
                    "fromdate": from_date,
                    "todate": to_date
                }
                resp = self.smart_connect.getCandleData(params)
                if resp and resp.get("status") and isinstance(resp.get("data"), list):
                    candles = []
                    for row in resp["data"]:
                        # row: [timestamp_str, open, high, low, close, volume]
                        try:
                            # Parse timestamp
                            ts_str = row[0]
                            # ISO or format "2026-10-25T09:15:00+05:30"
                            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            time_epoch = int(dt.timestamp())
                        except Exception:
                            time_epoch = int(time.time())

                        candles.append({
                            "time": time_epoch,
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "volume": float(row[5]) if len(row) > 5 else 0
                        })
                    if candles:
                        return candles
            except Exception as e:
                logger.warning(f"getCandleData API warning for token {symboltoken}: {e}")

        return []

    def _background_quote_poller(self):
        """
        Background poll: If WebSocket has not received ticks for >10 seconds
        and we are authenticated, poll active tokens via REST ltpData to ensure
        the UI is continuously updated with valid quotes.
        """
        while True:
            try:
                time.sleep(5)
                if self.is_authenticated and self.smart_connect:
                    now_ts = time.time()
                    # If websocket hasn't received ticks for a while
                    if not self.last_tick_time or (now_ts - self.last_tick_time > 10):
                        with self.ws_lock:
                            tokens = list(self.active_subscriptions.items())[:15]
                        
                        for tok, exch in tokens:
                            try:
                                exchange_name = "BSE" if exch in [3, 4] else "NSE"
                                quote = self.smart_connect.ltpData(exchange_name, "", tok)
                                if quote and quote.get("status") and "data" in quote:
                                    d = quote["data"]
                                    ltp = float(d.get("ltp", 0))
                                    if ltp > 0:
                                        self._dispatch_tick({
                                            "token": tok,
                                            "exchange_type": exch,
                                            "last_traded_price": int(ltp * 100),
                                            "high_price_of_the_day": int(d.get("high", ltp * 1.008) * 100),
                                            "low_price_of_the_day": int(d.get("low", ltp * 0.992) * 100),
                                            "open_price_of_the_day": int(d.get("open", ltp) * 100),
                                            "closed_price": int(d.get("close", ltp) * 100),
                                            "volume_trade_for_the_day": int(d.get("volume", 0)),
                                            "exchange_timestamp": int(time.time() * 1000)
                                        })
                            except Exception:
                                pass
                            time.sleep(0.3)
            except Exception as err:
                logger.debug(f"Quote poller notice: {err}")
