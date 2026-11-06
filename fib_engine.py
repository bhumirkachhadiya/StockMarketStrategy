"""
Centralized Fibonacci Strategy Calculation Engine
Strictly preserves the 4-level Fibonacci model and generates synchronized levels
for Scanner, Option Chain, Signals, and Live Chart with exact prices and P&L metrics.
"""
from typing import Dict, List, Any, Optional

class FibonacciEngine:
    RATIOS = [0, 0.236, 1.0, 1.618]

    @staticmethod
    def calculate_fib_levels(high: float, low: float) -> List[Dict[str, Any]]:
        """
        Calculate the 4-level Fibonacci rays:
        Fib A (H -> L): H - (diff * r)
        Fib B (L -> H): L + (diff * r)
        """
        diff = max(high - low, high * 0.005)  # Ensure non-zero spread
        levels = []

        for r in FibonacciEngine.RATIOS:
            levels.append({
                "name": f"Fib A ({r})",
                "ratio": r,
                "price": round(high - (diff * r), 2),
                "type": "resistance" if r in [0, 0.236] else "extension_down",
                "description": "High-to-Low Ray"
            })
            levels.append({
                "name": f"Fib B ({r})",
                "ratio": r,
                "price": round(low + (diff * r), 2),
                "type": "support" if r in [0, 0.236] else "extension_up",
                "description": "Low-to-High Ray"
            })

        # Sort levels descending by price
        return sorted(levels, key=lambda x: x["price"], reverse=True)

    @staticmethod
    def get_atm_strike(ltp: float, step: float) -> float:
        """Calculate the At-The-Money (ATM) strike price."""
        if step <= 0:
            step = 50.0
        return round(round(ltp / step) * step, 2)

    @classmethod
    def evaluate_strategy(
        cls,
        symbol: str,
        ltp: float,
        high: float,
        low: float,
        strike_step: float = 50.0,
        proximity_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Evaluate full Fibonacci strategy setup, calculating:
        - 6 Configured Strategy Price Levels:
            1. Stop Loss (SL)
            2. Entry Price
            3. Target 1 (T1)
            4. Target 2 (T2)
            5. Target 3 (T3)
            6. Target 4 (T4)
        - Exact distance to each level (₹ and %)
        - Hit / Not Hit status for each level
        - Current P&L points and percentage
        - Distance to next target & distance to SL
        - Direction (Bullish/Bearish) & Recommended Action
        """
        if ltp <= 0:
            ltp = max(high, low, 1.0)
        if high <= 0:
            high = ltp * 1.005
        if low <= 0 or low > high:
            low = min(ltp * 0.995, high * 0.995)

        diff = max(high - low, ltp * 0.005)
        levels = cls.calculate_fib_levels(high, low)

        # Dynamic proximity threshold: default 0.1% of LTP or specified absolute value
        threshold = proximity_threshold if (proximity_threshold is not None and proximity_threshold > 0) else max(round(ltp * 0.001, 2), 1.5)

        # Find nearest ray
        nearest_ray = min(levels, key=lambda x: abs(ltp - x["price"]))

        # Determine Bullish or Bearish setup
        mid_point = (high + low) / 2.0
        is_bullish = nearest_ray["price"] >= ltp or ltp <= mid_point

        if is_bullish:
            direction = "BULLISH"
            option_type = "CE"
            setup_type = "Support Bounce"
            entry_level = round(nearest_ray["price"] if nearest_ray["price"] >= ltp else low + (diff * 0.236), 2)
            stop_loss = round(min(low, entry_level - (diff * 0.15)), 2)
            target_1 = round(high - (diff * 0.236), 2)
            if target_1 <= entry_level:
                target_1 = round(entry_level + (diff * 0.236), 2)
            target_2 = round(high, 2)
            if target_2 <= target_1:
                target_2 = round(target_1 + (diff * 0.236), 2)
            target_3 = round(low + (diff * 1.618), 2)
            target_4 = round(high + diff, 2)
        else:
            direction = "BEARISH"
            option_type = "PE"
            setup_type = "Resistance Rejection"
            entry_level = round(nearest_ray["price"] if nearest_ray["price"] <= ltp else high - (diff * 0.236), 2)
            stop_loss = round(max(high, entry_level + (diff * 0.15)), 2)
            target_1 = round(low + (diff * 0.236), 2)
            if target_1 >= entry_level:
                target_1 = round(entry_level - (diff * 0.236), 2)
            target_2 = round(low, 2)
            if target_2 >= target_1:
                target_2 = round(target_1 - (diff * 0.236), 2)
            target_3 = round(high - (diff * 1.618), 2)
            target_4 = round(low - diff, 2)

        # Distances to key levels
        dist_entry = abs(ltp - entry_level)
        dist_t1 = abs(ltp - target_1)
        dist_t2 = abs(ltp - target_2)
        dist_sl = abs(ltp - stop_loss)

        # Hit statuses and P&L calculations
        if is_bullish:
            entry_hit = ltp >= entry_level
            t1_hit = ltp >= target_1
            t2_hit = ltp >= target_2
            t3_hit = ltp >= target_3
            t4_hit = ltp >= target_4
            sl_hit = ltp <= stop_loss
            pnl_points = round(ltp - entry_level, 2)

            if sl_hit:
                status = "STOP_LOSS_HIT"
                status_text = "Stop Loss Hit"
                status_color = "red"
            elif dist_sl <= threshold:
                status = "NEAR_STOP_LOSS"
                status_text = "Near Stop Loss"
                status_color = "red"
            elif t2_hit:
                status = "TARGET_2_ACHIEVED"
                status_text = "Target 2 Achieved"
                status_color = "emerald"
            elif dist_t2 <= threshold:
                status = "NEAR_TARGET_2"
                status_text = "Near Target 2"
                status_color = "green"
            elif t1_hit:
                status = "TARGET_1_ACHIEVED"
                status_text = "Target 1 Achieved"
                status_color = "emerald"
            elif dist_t1 <= threshold:
                status = "NEAR_TARGET_1"
                status_text = "Near Target 1"
                status_color = "green"
            elif entry_hit:
                status = "ENTRY_TRIGGERED"
                status_text = "Entry Triggered"
                status_color = "cyan"
            elif dist_entry <= threshold:
                status = "NEAR_ENTRY"
                status_text = "Near Entry (Touch Zone)"
                status_color = "yellow"
            else:
                status = "WAITING_FOR_ENTRY"
                status_text = "Waiting for Entry"
                status_color = "slate"

            # Determine next target
            if not t1_hit:
                next_target_name = "Target 1"
                dist_to_next_target = round(target_1 - ltp, 2)
            elif not t2_hit:
                next_target_name = "Target 2"
                dist_to_next_target = round(target_2 - ltp, 2)
            elif not t3_hit:
                next_target_name = "Target 3"
                dist_to_next_target = round(target_3 - ltp, 2)
            else:
                next_target_name = "Target 4"
                dist_to_next_target = round(target_4 - ltp, 2)
            dist_to_sl = round(ltp - stop_loss, 2)
        else:
            entry_hit = ltp <= entry_level
            t1_hit = ltp <= target_1
            t2_hit = ltp <= target_2
            t3_hit = ltp <= target_3
            t4_hit = ltp <= target_4
            sl_hit = ltp >= stop_loss
            pnl_points = round(entry_level - ltp, 2)

            if sl_hit:
                status = "STOP_LOSS_HIT"
                status_text = "Stop Loss Hit"
                status_color = "red"
            elif dist_sl <= threshold:
                status = "NEAR_STOP_LOSS"
                status_text = "Near Stop Loss"
                status_color = "red"
            elif t2_hit:
                status = "TARGET_2_ACHIEVED"
                status_text = "Target 2 Achieved"
                status_color = "emerald"
            elif dist_t2 <= threshold:
                status = "NEAR_TARGET_2"
                status_text = "Near Target 2"
                status_color = "green"
            elif t1_hit:
                status = "TARGET_1_ACHIEVED"
                status_text = "Target 1 Achieved"
                status_color = "emerald"
            elif dist_t1 <= threshold:
                status = "NEAR_TARGET_1"
                status_text = "Near Target 1"
                status_color = "green"
            elif entry_hit:
                status = "ENTRY_TRIGGERED"
                status_text = "Entry Triggered"
                status_color = "cyan"
            elif dist_entry <= threshold:
                status = "NEAR_ENTRY"
                status_text = "Near Entry (Touch Zone)"
                status_color = "yellow"
            else:
                status = "WAITING_FOR_ENTRY"
                status_text = "Waiting for Entry"
                status_color = "slate"

            if not t1_hit:
                next_target_name = "Target 1"
                dist_to_next_target = round(ltp - target_1, 2)
            elif not t2_hit:
                next_target_name = "Target 2"
                dist_to_next_target = round(ltp - target_2, 2)
            elif not t3_hit:
                next_target_name = "Target 3"
                dist_to_next_target = round(ltp - target_3, 2)
            else:
                next_target_name = "Target 4"
                dist_to_next_target = round(ltp - target_4, 2)
            dist_to_sl = round(stop_loss - ltp, 2)

        pnl_pct = round((pnl_points / entry_level) * 100.0, 2) if entry_level > 0 else 0.0
        atm_strike = cls.get_atm_strike(ltp, strike_step)
        action_label = f"BUY {int(atm_strike) if atm_strike == int(atm_strike) else atm_strike} {option_type}"

        # 6 Strategy price levels for chart overlays with exact price and status metrics
        strategy_levels = [
            {
                "name": "Stop Loss (SL)",
                "code": "SL",
                "price": stop_loss,
                "color": "#ef4444",
                "lineStyle": "dashed",
                "distance": round(abs(ltp - stop_loss), 2),
                "distance_pct": round(abs(ltp - stop_loss) / ltp * 100.0, 2),
                "is_hit": sl_hit,
                "hit_status": "Hit" if sl_hit else "Pending"
            },
            {
                "name": "Entry Price",
                "code": "ENTRY",
                "price": entry_level,
                "color": "#eab308",
                "lineStyle": "solid",
                "distance": round(abs(ltp - entry_level), 2),
                "distance_pct": round(abs(ltp - entry_level) / ltp * 100.0, 2),
                "is_hit": entry_hit,
                "hit_status": "Triggered" if entry_hit else "Pending"
            },
            {
                "name": "Target 1 (T1)",
                "code": "T1",
                "price": target_1,
                "color": "#22c55e",
                "lineStyle": "dashed",
                "distance": round(abs(ltp - target_1), 2),
                "distance_pct": round(abs(ltp - target_1) / ltp * 100.0, 2),
                "is_hit": t1_hit,
                "hit_status": "Achieved" if t1_hit else "Pending"
            },
            {
                "name": "Target 2 (T2)",
                "code": "T2",
                "price": target_2,
                "color": "#10b981",
                "lineStyle": "solid",
                "distance": round(abs(ltp - target_2), 2),
                "distance_pct": round(abs(ltp - target_2) / ltp * 100.0, 2),
                "is_hit": t2_hit,
                "hit_status": "Achieved" if t2_hit else "Pending"
            },
            {
                "name": "Target 3 (T3)",
                "code": "T3",
                "price": target_3,
                "color": "#06b6d4",
                "lineStyle": "solid",
                "distance": round(abs(ltp - target_3), 2),
                "distance_pct": round(abs(ltp - target_3) / ltp * 100.0, 2),
                "is_hit": t3_hit,
                "hit_status": "Achieved" if t3_hit else "Pending"
            },
            {
                "name": "Target 4 (T4)",
                "code": "T4",
                "price": target_4,
                "color": "#3b82f6",
                "lineStyle": "solid",
                "distance": round(abs(ltp - target_4), 2),
                "distance_pct": round(abs(ltp - target_4) / ltp * 100.0, 2),
                "is_hit": t4_hit,
                "hit_status": "Achieved" if t4_hit else "Pending"
            }
        ]

        return {
            "symbol": symbol,
            "ltp": round(ltp, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "direction": direction,
            "option_type": option_type,
            "setup_type": setup_type,
            "atm_strike": atm_strike,
            "action_label": action_label,
            "status": status,
            "status_text": status_text,
            "status_color": status_color,
            "entry": entry_level,
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2,
            "target_3": target_3,
            "target_4": target_4,
            "pnl_points": pnl_points,
            "pnl_pct": pnl_pct,
            "next_target_name": next_target_name,
            "dist_to_next_target": dist_to_next_target,
            "dist_to_sl": dist_to_sl,
            "distance_entry": round(dist_entry, 2),
            "distance_t1": round(dist_t1, 2),
            "distance_t2": round(dist_t2, 2),
            "distance_sl": round(dist_sl, 2),
            "threshold": threshold,
            "nearest_ray": nearest_ray,
            "fib_rays": levels,
            "strategy_levels": strategy_levels
        }

    @classmethod
    def evaluate_option_contract_strategy(
        cls,
        symbol: str,
        option_ltp: float,
        option_high: Optional[float] = None,
        option_low: Optional[float] = None,
        option_type: str = "CE"
    ) -> Dict[str, Any]:
        """
        Calculate exact strategy price levels for an individual Option Contract.
        Entry, SL, and Targets correspond to the option contract's own premium range.
        """
        opt_ltp = max(option_ltp, 1.0)
        opt_high = option_high if (option_high and option_high > opt_ltp) else round(opt_ltp * 1.15, 2)
        opt_low = option_low if (option_low and option_low < opt_ltp and option_low > 0) else round(opt_ltp * 0.85, 2)
        diff = max(opt_high - opt_low, opt_ltp * 0.10)

        # In option buying, direction is Long
        entry = round(opt_ltp, 2)
        # 15% risk / Stop Loss
        stop_loss = round(max(entry - (diff * 0.5), entry * 0.80), 2)
        target_1 = round(entry + (diff * 0.618), 2)
        target_2 = round(entry + diff, 2)
        target_3 = round(entry + (diff * 1.618), 2)
        target_4 = round(entry + (diff * 2.618), 2)

        sl_hit = opt_ltp <= stop_loss
        t1_hit = opt_ltp >= target_1
        t2_hit = opt_ltp >= target_2
        t3_hit = opt_ltp >= target_3
        t4_hit = opt_ltp >= target_4

        strategy_levels = [
            {
                "name": "Stop Loss (SL)", "code": "SL", "price": stop_loss, "color": "#ef4444", "lineStyle": "dashed",
                "distance": round(abs(opt_ltp - stop_loss), 2), "distance_pct": round(abs(opt_ltp - stop_loss) / opt_ltp * 100.0, 2),
                "is_hit": sl_hit, "hit_status": "Hit" if sl_hit else "Pending"
            },
            {
                "name": "Entry Price", "code": "ENTRY", "price": entry, "color": "#eab308", "lineStyle": "solid",
                "distance": 0.0, "distance_pct": 0.0,
                "is_hit": True, "hit_status": "Active"
            },
            {
                "name": "Target 1 (T1)", "code": "T1", "price": target_1, "color": "#22c55e", "lineStyle": "dashed",
                "distance": round(abs(opt_ltp - target_1), 2), "distance_pct": round(abs(opt_ltp - target_1) / opt_ltp * 100.0, 2),
                "is_hit": t1_hit, "hit_status": "Achieved" if t1_hit else "Pending"
            },
            {
                "name": "Target 2 (T2)", "code": "T2", "price": target_2, "color": "#10b981", "lineStyle": "solid",
                "distance": round(abs(opt_ltp - target_2), 2), "distance_pct": round(abs(opt_ltp - target_2) / opt_ltp * 100.0, 2),
                "is_hit": t2_hit, "hit_status": "Achieved" if t2_hit else "Pending"
            },
            {
                "name": "Target 3 (T3)", "code": "T3", "price": target_3, "color": "#06b6d4", "lineStyle": "solid",
                "distance": round(abs(opt_ltp - target_3), 2), "distance_pct": round(abs(opt_ltp - target_3) / opt_ltp * 100.0, 2),
                "is_hit": t3_hit, "hit_status": "Achieved" if t3_hit else "Pending"
            },
            {
                "name": "Target 4 (T4)", "code": "T4", "price": target_4, "color": "#3b82f6", "lineStyle": "solid",
                "distance": round(abs(opt_ltp - target_4), 2), "distance_pct": round(abs(opt_ltp - target_4) / opt_ltp * 100.0, 2),
                "is_hit": t4_hit, "hit_status": "Achieved" if t4_hit else "Pending"
            }
        ]

        return {
            "symbol": symbol,
            "ltp": opt_ltp,
            "high": opt_high,
            "low": opt_low,
            "direction": "LONG",
            "option_type": option_type,
            "setup_type": "Option Momentum Ray",
            "entry": entry,
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2,
            "target_3": target_3,
            "target_4": target_4,
            "pnl_points": 0.0,
            "pnl_pct": 0.0,
            "next_target_name": "Target 1",
            "dist_to_next_target": round(target_1 - opt_ltp, 2),
            "dist_to_sl": round(opt_ltp - stop_loss, 2),
            "strategy_levels": strategy_levels
        }
