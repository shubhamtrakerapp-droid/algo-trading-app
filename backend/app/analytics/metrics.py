import math
from datetime import datetime, timezone
from typing import List, Dict, Any


def compute_trading_metrics(trades: List[Dict[str, Any]], initial_capital: float = 100000.0) -> Dict[str, Any]:
    """
    Computes comprehensive performance analytics for paper trades or backtest runs.
    """
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "net_profit": 0.0,
            "profit_factor": 0.0,
            "avg_profit_per_trade": 0.0,
            "avg_loss_per_trade": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_percent": 0.0,
            "largest_winning_trade": 0.0,
            "largest_losing_trade": 0.0,
            "total_brokerage_charges": 0.0,
            "consecutive_wins_max": 0,
            "consecutive_losses_max": 0,
            "daily_summary": [],
            "monthly_summary": [],
            "equity_curve": [{"trade": 0, "equity": initial_capital, "time": "Initial"}]
        }

    wins = [t for t in trades if float(t.get("net_pnl") or 0.0) > 0]
    losses = [t for t in trades if float(t.get("net_pnl") or 0.0) <= 0]
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = round((win_count / total_trades) * 100.0, 2)

    gross_profit = round(sum(float(t.get("gross_pnl") or 0.0) for t in trades if float(t.get("gross_pnl") or 0.0) > 0), 2)
    gross_loss = round(abs(sum(float(t.get("gross_pnl") or 0.0) for t in trades if float(t.get("gross_pnl") or 0.0) < 0)), 2)
    total_charges = round(sum(float(t.get("charges") if t.get("charges") is not None else (t.get("total_charges") or 0.0)) for t in trades), 2)
    net_profit = round(sum(float(t.get("net_pnl") or 0.0) for t in trades), 2)

    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    avg_profit = round(sum(float(t.get("net_pnl") or 0.0) for t in wins) / win_count, 2) if win_count > 0 else 0.0
    avg_loss = round(sum(float(t.get("net_pnl") or 0.0) for t in losses) / loss_count, 2) if loss_count > 0 else 0.0

    largest_win = round(max([float(t.get("net_pnl") or 0.0) for t in wins], default=0.0), 2)
    largest_loss = round(min([float(t.get("net_pnl") or 0.0) for t in losses], default=0.0), 2)

    # Max Drawdown & Equity Curve
    current_equity = initial_capital
    peak_equity = initial_capital
    max_dd = 0.0
    max_dd_pct = 0.0
    equity_curve = [{"trade": 0, "equity": initial_capital, "time": "Start"}]

    # Consecutive streak counters
    cur_consec_wins = 0
    max_consec_wins = 0
    cur_consec_losses = 0
    max_consec_losses = 0

    # Daily & Monthly aggregation
    daily_map: Dict[str, Dict[str, Any]] = {}
    monthly_map: Dict[str, Dict[str, Any]] = {}

    for idx, t in enumerate(trades, 1):
        gross = float(t.get("gross_pnl") if t.get("gross_pnl") is not None else 0.0)
        raw_chg = t.get("charges") if t.get("charges") is not None else t.get("total_charges")
        chg = float(raw_chg if raw_chg is not None else 0.0)
        raw_net = t.get("net_pnl")
        net = float(raw_net if raw_net is not None else (gross - chg))

        current_equity = round(current_equity + net, 2)
        equity_curve.append({
            "trade": idx,
            "equity": current_equity,
            "net_pnl": net,
            "time": str(t.get("exit_time", f"Trade {idx}"))
        })

        if current_equity > peak_equity:
            peak_equity = current_equity

        dd = peak_equity - current_equity
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = round((dd / peak_equity) * 100.0, 2) if peak_equity > 0 else 0.0

        if net > 0:
            cur_consec_wins += 1
            cur_consec_losses = 0
            if cur_consec_wins > max_consec_wins:
                max_consec_wins = cur_consec_wins
        else:
            cur_consec_losses += 1
            cur_consec_wins = 0
            if cur_consec_losses > max_consec_losses:
                max_consec_losses = cur_consec_losses

        # Date aggregations
        raw_time = t.get("exit_time")
        if isinstance(raw_time, datetime):
            day_str = raw_time.strftime("%Y-%m-%d")
            month_str = raw_time.strftime("%Y-%m")
        elif isinstance(raw_time, str) and len(raw_time) >= 10:
            day_str = raw_time[:10]
            month_str = raw_time[:7]
        else:
            day_str = "Unknown"
            month_str = "Unknown"

        # Daily
        if day_str not in daily_map:
            daily_map[day_str] = {
                "date": day_str,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "grossProfit": 0.0,
                "grossLoss": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "charges": 0.0,
                "pnl": 0.0,
                "net_pnl": 0.0,
            }
        entry = daily_map[day_str]
        entry["trades"] += 1
        if gross > 0:
            entry["grossProfit"] = round(entry["grossProfit"] + gross, 2)
            entry["gross_profit"] = round(entry["gross_profit"] + gross, 2)
        elif gross < 0:
            entry["grossLoss"] = round(entry["grossLoss"] + abs(gross), 2)
            entry["gross_loss"] = round(entry["gross_loss"] + abs(gross), 2)

        entry["charges"] = round(entry["charges"] + chg, 2)
        entry["pnl"] = round(entry["pnl"] + net, 2)
        entry["net_pnl"] = round(entry["net_pnl"] + net, 2)

        if net > 0:
            entry["wins"] += 1
        else:
            entry["losses"] += 1

        entry["win_rate"] = round((entry["wins"] / entry["trades"]) * 100.0, 1)

        # Monthly
        if month_str not in monthly_map:
            monthly_map[month_str] = {"month": month_str, "trades": 0, "pnl": 0.0, "wins": 0}
        monthly_map[month_str]["trades"] += 1
        monthly_map[month_str]["pnl"] = round(monthly_map[month_str]["pnl"] + net, 2)
        if net > 0:
            monthly_map[month_str]["wins"] += 1

    daily_summary = sorted(daily_map.values(), key=lambda x: x["date"])
    monthly_summary = sorted(monthly_map.values(), key=lambda x: x["month"])
    for m in monthly_summary:
        m["win_rate"] = round((m["wins"] / m["trades"]) * 100.0, 1)

    return {
        "total_trades": total_trades,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit": net_profit,
        "profit_factor": profit_factor,
        "avg_profit_per_trade": avg_profit,
        "avg_loss_per_trade": avg_loss,
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_percent": max_dd_pct,
        "largest_winning_trade": largest_win,
        "largest_losing_trade": largest_loss,
        "total_brokerage_charges": total_charges,
        "consecutive_wins_max": max_consec_wins,
        "consecutive_losses_max": max_consec_losses,
        "daily_summary": daily_summary,
        "monthly_summary": monthly_summary,
        "equity_curve": equity_curve
    }
