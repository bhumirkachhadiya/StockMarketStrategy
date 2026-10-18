from flask import Flask, send_from_directory, request, jsonify
from flask_socketio import SocketIO, emit
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import threading
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

API_KEY = "MRx8rHZh"
CLIENT_ID = "AAAA492357"
PIN = "6405"

obj = None
sws = None

CORE_INSTRUMENTS = [
    {"exchangeType": 1, "tokens": ["26000", "26009", "26037", "26013"]}, 
    {"exchangeType": 3, "tokens": ["51", "52"]},                          
    {"exchangeType": 1, "tokens": ["2885", "11536", "1594", "3045", "1333", "1660"]} 
]

INSTRUMENT_LOOKUP = {
    "26000": {"symbol": "NIFTY", "exchange": "NSE"},
    "26009": {"symbol": "BANKNIFTY", "exchange": "NSE"},
    "26037": {"symbol": "FINNIFTY", "exchange": "NSE"},
    "26013": {"symbol": "MIDCPNIFTY", "exchange": "NSE"},
    "51":    {"symbol": "SENSEX", "exchange": "BSE"},
    "52":    {"symbol": "BANKEX", "exchange": "BSE"},
    "2885":  {"symbol": "RELIANCE", "exchange": "NSE"},
    "11536": {"symbol": "TCS", "exchange": "NSE"},
    "1594":  {"symbol": "INFY", "exchange": "NSE"},
    "3045":  {"symbol": "SBIN", "exchange": "NSE"},
    "1333":  {"symbol": "HDFCBANK", "exchange": "NSE"},
    "1660":  {"symbol": "ICICIBANK", "exchange": "NSE"}
}

# Add global CORS headers to allow Netlify to communicate without preflight blocks
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,bypass-tunnel-reminder'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def api_login():
    if request.method == 'OPTIONS':
        return jsonify({'status': True}), 200

    global obj, sws
    data_req = request.json or {}
    totp_code = data_req.get('totp')
    
    if not totp_code:
        return jsonify({"status": False, "message": "TOTP code is required."}), 400

    try:
        print(f"\n[Angel One] Authenticating via Web UI with TOTP: {totp_code}")
        obj = SmartConnect(api_key=API_KEY)
        session_data = obj.generateSession(CLIENT_ID, PIN, totp_code)
        
        if session_data and session_data.get('status'):
            auth_token = session_data['data']['jwtToken']
            feed_token = session_data['data']['feedToken']
            print("[Angel One] Web Authentication successful!")

            try:
                for token, info in INSTRUMENT_LOOKUP.items():
                    quote = obj.ltpData(info["exchange"], info["symbol"], token)
                    if quote and 'data' in quote:
                        close_price = quote['data'].get('ltp', 0)
                        if close_price > 0:
                            socketio.emit('market_tick', {
                                "token": token,
                                "last_traded_price": close_price * 100,
                                "high": close_price * 1.008 * 100,
                                "low": close_price * 0.992 * 100
                            })
            except Exception as q_err:
                print("[Quote Fetch Notice]:", q_err)

            sws = SmartWebSocketV2(auth_token, CLIENT_ID, API_KEY, feed_token)

            def on_data(*args):
                try:
                    message = args[-1] if len(args) > 0 else None
                    if isinstance(message, dict):
                        socketio.emit('market_tick', message)
                except Exception as e:
                    print("[Tick Parse Error]:", e)

            def on_open(*args):
                print("[Angel One WebSocket] Connected! Subscribing to core market stream...")
                for batch in CORE_INSTRUMENTS:
                    sws.subscribe(correlation_id="core_stream", mode=1, token_list=[batch])

            def on_error(*args):
                print("[Angel One WebSocket Error]:", args)

            def on_close(*args):
                print("[Angel One WebSocket] Connection closed.")

            sws._on_open = on_open
            sws._on_data = on_data
            sws._on_error = on_error
            sws._on_close = on_close

            threading.Thread(target=sws.connect, daemon=True).start()
            return jsonify({"status": True, "message": "Authentication successful!"})
        else:
            return jsonify({"status": False, "message": str(session_data)}), 400
    except Exception as e:
        return jsonify({"status": False, "message": str(e)}), 500

@app.route('/')
def index():
    return send_from_directory(os.path.dirname(__file__), 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
