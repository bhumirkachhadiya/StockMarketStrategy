import time
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import threading

# --- UPDATE YOUR ANGEL ONE CREDENTIALS HERE ---
API_KEY = "MRx8rHZh"
CLIENT_ID = "AAAA492357"
PIN = "6405"

live_market_store = {
    "26000": {"symbol": "NIFTY SPOT", "ltp": 22450.00, "high": 22520.00, "low": 22380.00},
    "26009": {"symbol": "BANKNIFTY SPOT", "ltp": 47800.00, "high": 48150.00, "low": 47620.00},
    "2885":  {"symbol": "RELIANCE SPOT", "ltp": 2880.00, "high": 2910.00, "low": 2855.00},
    "11536": {"symbol": "TCS SPOT", "ltp": 3950.00, "high": 3980.00, "low": 3920.00},
    "1594":  {"symbol": "INFY SPOT", "ltp": 1620.00, "high": 1640.00, "low": 1605.00}
}

def calculate_fib_levels(H, L):
    diff = H - L
    ratios = [0, 0.236, 1.0, 1.618]
    levels = []
    for r in ratios:
        levels.append({"name": f"Fib A ({r})", "price": round(H - (diff * r), 2)})
        levels.append({"name": f"Fib B ({r})", "price": round(L + (diff * r), 2)})
    return sorted(levels, key=lambda x: x["price"], reverse=True)

def generate_layout():
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1)
    )
    
    layout["header"].update(
        Panel("[bold cyan]FIB-PRECISION F&O INDIA - LIVE MULTI-INSTRUMENT MATRIX[/bold cyan]", style="bold white on blue")
    )

    table = Table(title="Live Multi-Instrument Fibonacci Level Matrix", expand=True)
    table.add_column("Token", style="dim")
    table.add_column("Symbol / Instrument", style="bold white")
    table.add_column("Live LTP (₹)", justify="right", style="bold green")
    table.add_column("Prev High (₹)", justify="right", style="blue")
    table.add_column("Prev Low (₹)", justify="right", style="purple")
    table.add_column("Nearest Fib Level", justify="center", style="yellow")
    table.add_column("Level Price (₹)", justify="right")
    table.add_column("Distance (₹)", justify="right")
    table.add_column("Status", justify="center")

    for token, item in live_market_store.items():
        fibs = calculate_fib_levels(item["high"], item["low"])
        nearest = min(fibs, key=lambda f: abs(item["ltp"] - f["price"]))
        dist = abs(item["ltp"] - nearest["price"])
        status = "[bold red]TOUCH ZONE[/bold red]" if dist <= 1.50 else ("[bold green]NEAR[/bold green]" if dist <= 5.0 else "[dim]ACTIVE[/dim]")
        
        table.add_row(
            token,
            item["symbol"],
            f"₹{item['ltp']:.2f}",
            f"₹{item['high']:.2f}",
            f"₹{item['low']:.2f}",
            nearest["name"],
            f"₹{nearest['price']:.2f}",
            f"₹{dist:.2f}",
            status
        )

    layout["main"].update(Panel(table, border_style="cyan"))
    return layout

def init_angel_one():
    global live_market_store
    try:
        obj = SmartConnect(api_key=API_KEY)
        data = obj.generateSession(CLIENT_ID, PIN)
        if data and data.get('status'):
            auth_token = data['data']['jwtToken']
            feed_token = obj.feedToken
            sws = SmartWebSocketV2(auth_token, CLIENT_ID, API_KEY, feed_token)

            def on_data(wsclass, message):
                if 'token' in message and 'last_traded_price' in message:
                    tok = str(message['token'])
                    if tok in live_market_store:
                        live_market_store[tok]['ltp'] = message['last_traded_price'] / 100.0

            def on_open(wsclass):
                tokens = list(live_market_store.keys())
                sws.subscribe(correlation_id="terminal_stream", mode=1, token_list=[{"exchangeType": 1, "tokens": tokens}])

            sws._on_open = on_open
            sws._on_data = on_data
            threading.Thread(target=sws.connect, daemon=True).start()
    except Exception as e:
        print("Connection Error:", e)

if __name__ == "__main__":
    init_angel_one()
    console = Console()
    with Live(generate_layout(), refresh_per_second=4, console=console) as live:
        while True:
            time.sleep(0.25)
            live.update(generate_layout())
