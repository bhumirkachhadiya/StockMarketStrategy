import time
import os
import threading
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.console import Console

from fib_engine import FibonacciEngine
from angel_service import AngelService
from instrument_manager import InstrumentManager

# Use centralized AngelService and InstrumentManager
angel_service = AngelService()
instrument_mgr = InstrumentManager()

live_market_store = {
    "26000": {"symbol": "NIFTY", "name": "NIFTY 50", "ltp": 24150.00, "high": 24220.00, "low": 24080.00, "step": 50},
    "26009": {"symbol": "BANKNIFTY", "name": "BANK NIFTY", "ltp": 51200.00, "high": 51450.00, "low": 50950.00, "step": 100},
    "26037": {"symbol": "FINNIFTY", "name": "FIN NIFTY", "ltp": 23800.00, "high": 23920.00, "low": 23690.00, "step": 50},
    "2885":  {"symbol": "RELIANCE", "name": "RELIANCE", "ltp": 1320.00, "high": 1332.00, "low": 1312.00, "step": 20},
    "11536": {"symbol": "TCS", "name": "TCS", "ltp": 4120.00, "high": 4150.00, "low": 4095.00, "step": 20},
    "1594":  {"symbol": "INFY", "name": "INFY", "ltp": 1840.00, "high": 1858.00, "low": 1828.00, "step": 10},
    "3045":  {"symbol": "SBIN", "name": "SBIN", "ltp": 820.00, "high": 828.00, "low": 814.00, "step": 10},
    "1333":  {"symbol": "HDFCBANK", "name": "HDFCBANK", "ltp": 1740.00, "high": 1755.00, "low": 1730.00, "step": 10}
}

def on_tick(tick):
    tok = str(tick.get("token"))
    if tok in live_market_store:
        live_market_store[tok]["ltp"] = tick.get("ltp", live_market_store[tok]["ltp"])
        if tick.get("high", 0) > 0:
            live_market_store[tok]["high"] = tick["high"]
        if tick.get("low", 0) > 0:
            live_market_store[tok]["low"] = tick["low"]

angel_service.register_tick_callback(on_tick)

def generate_layout():
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1)
    )
    
    auth_str = "[bold green]CONNECTED[/bold green]" if angel_service.is_authenticated else "[bold red]DISCONNECTED[/bold red]"
    layout["header"].update(
        Panel(f"[bold cyan]FIB-PRECISION F&O INDIA - LIVE MULTI-INSTRUMENT MATRIX[/bold cyan] | SmartAPI: {auth_str}", style="bold white on blue")
    )

    table = Table(title="Live Multi-Instrument Fibonacci Level Matrix", expand=True)
    table.add_column("Token", style="dim")
    table.add_column("Symbol / Instrument", style="bold white")
    table.add_column("Live LTP (₹)", justify="right", style="bold green")
    table.add_column("Direction", justify="center")
    table.add_column("Actionable", justify="center", style="yellow")
    table.add_column("Entry (₹)", justify="right", style="yellow")
    table.add_column("Stop Loss (₹)", justify="right", style="red")
    table.add_column("Target 1 (₹)", justify="right", style="green")
    table.add_column("Target 2 (₹)", justify="right", style="emerald")
    table.add_column("Distance (₹)", justify="right")
    table.add_column("Status", justify="center")

    for token, item in live_market_store.items():
        res = FibonacciEngine.evaluate_strategy(
            symbol=item["symbol"],
            ltp=item["ltp"],
            high=item["high"],
            low=item["low"],
            strike_step=item.get("step", 50)
        )
        
        status_style = "[bold red]TOUCH ZONE[/bold red]" if "NEAR_ENTRY" in res["status"] or "ENTRY_TRIGGERED" in res["status"] else (
            "[bold green]TARGET HIT[/bold green]" if "TARGET" in res["status"] else "[dim]WAITING[/dim]"
        )

        dir_style = "[bold green]BULLISH (CE)[/bold green]" if res["direction"] == "BULLISH" else "[bold red]BEARISH (PE)[/bold red]"
        
        table.add_row(
            token,
            item["symbol"],
            f"₹{res['ltp']:.2f}",
            dir_style,
            res["action_label"],
            f"₹{res['entry']:.2f}",
            f"₹{res['stop_loss']:.2f}",
            f"₹{res['target_1']:.2f}",
            f"₹{res['target_2']:.2f}",
            f"₹{res['distance_entry']:.2f}",
            status_style
        )

    layout["main"].update(Panel(table, border_style="cyan"))
    return layout

if __name__ == "__main__":
    console = Console()
    with Live(generate_layout(), refresh_per_second=4, console=console) as live:
        while True:
            time.sleep(0.25)
            live.update(generate_layout())
