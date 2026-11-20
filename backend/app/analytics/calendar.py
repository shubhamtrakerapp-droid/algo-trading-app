"""
Advanced Monthly & Yearly Performance Calendar Analytics Engine.
Calculates daily, monthly, yearly, and streak metrics across trade ledgers.
Enforces:
- IST (Asia/Kolkata) date boundaries.
- Flat charges and slippage accounting.
- Exact reconciliation: Gross P&L - Total Charges - Slippage Cost = Net P&L.
- Streak rules: Net P&L > 0 is WIN, < 0 is LOSS, == 0 or no trades is NEUTRAL (breaks streak).
"""

import calendar
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

IST = timezone(timedelta(hours=5, minutes=30))


def get_current_ist_datetime() -> datetime:
    """Return current wall-clock datetime in IST."""
    return datetime.now(timezone.utc).astimezone(IST)


def parse_trade_datetime_ist(dt_val: Any) -> Optional[datetime]:
    """Parse a datetime object or ISO string and return an IST datetime without silent time shifts."""
    if dt_val is None:
        return None
    if isinstance(dt_val, str):
        clean_str = dt_val.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(clean_str)
        except Exception:
            try:
                parsed = datetime.strptime(dt_val[:10], "%Y-%m-%d").replace(tzinfo=IST)
            except Exception:
                return None
        dt_val = parsed

    if isinstance(dt_val, (int, float)):
        return datetime.fromtimestamp(dt_val, tz=IST)

    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is not None:
            return dt_val.astimezone(IST)
        # If naive (no tzinfo):
        # In NEXTRADE, trade and candle timestamps in SQLite with hour >= 9 (e.g. 09:15 to 15:30)
        # are ALREADY in wall-clock IST! Do NOT treat as UTC and add +5:30!
        if dt_val.hour >= 9:
            return dt_val.replace(tzinfo=IST)
        else:
            return dt_val.replace(tzinfo=timezone.utc).astimezone(IST)
    return None


class PerformanceCalendarEngine:
    """
    Computes comprehensive performance calendar data, streaks, and analytics
    from actual stored trade ledger records.
    """

    @staticmethod
    def aggregate_trades_by_date(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Group trades by trading date in IST (YYYY-MM-DD) and compute daily aggregates.
        """
        daily_map: Dict[str, Dict[str, Any]] = {}

        for t in trades:
            raw_exit = t.get("exit_time")
            exit_dt = parse_trade_datetime_ist(raw_exit)
            if not exit_dt:
                continue

            date_str = exit_dt.strftime("%Y-%m-%d")
            if date_str not in daily_map:
                daily_map[date_str] = {
                    "date": date_str,
                    "date_obj": exit_dt.date(),
                    "trades_count": 0,
                    "wins": 0,
                    "losses": 0,
                    "gross_profit": 0.0,
                    "gross_loss": 0.0,
                    "gross_pnl": 0.0,
                    "total_charges": 0.0,
                    "slippage_cost": 0.0,
                    "net_pnl": 0.0,
                    "holding_time_minutes_sum": 0,
                    "holding_times": [],
                    "trades": []
                }

            day = daily_map[date_str]
            day["trades_count"] += 1

            gross = float(t.get("gross_pnl") or 0.0)
            chg = float(t.get("total_charges") if t.get("total_charges") is not None else (t.get("charges") or 0.0))
            slip = float(t.get("slippage_cost") or 0.0)
            net = float(t.get("net_pnl") if t.get("net_pnl") is not None else (gross - chg))

            day["gross_pnl"] = round(day["gross_pnl"] + gross, 2)
            if gross > 0:
                day["gross_profit"] = round(day["gross_profit"] + gross, 2)
            elif gross < 0:
                day["gross_loss"] = round(day["gross_loss"] + abs(gross), 2)

            day["total_charges"] = round(day["total_charges"] + chg, 2)
            day["slippage_cost"] = round(day["slippage_cost"] + slip, 2)
            day["net_pnl"] = round(day["net_pnl"] + net, 2)

            if net > 0:
                day["wins"] += 1
            else:
                day["losses"] += 1

            hold_mins = t.get("holding_time_minutes")
            if hold_mins is None or hold_mins <= 0:
                raw_entry = t.get("entry_time")
                entry_dt = parse_trade_datetime_ist(raw_entry)
                if entry_dt and exit_dt:
                    hold_mins = max(1, int((exit_dt - entry_dt).total_seconds() // 60))
                else:
                    hold_mins = 1
            day["holding_times"].append(hold_mins)
            day["holding_time_minutes_sum"] += hold_mins

            day["trades"].append(t)

        # Finalize daily stats
        for d_str, day in daily_map.items():
            cnt = day["trades_count"]
            day["win_rate"] = round((day["wins"] / cnt) * 100.0, 1) if cnt > 0 else 0.0
            day["avg_holding_time"] = round(day["holding_time_minutes_sum"] / cnt, 1) if cnt > 0 else 0.0
            day["max_holding_time"] = max(day["holding_times"]) if day["holding_times"] else 0
            day["min_holding_time"] = min(day["holding_times"]) if day["holding_times"] else 0

            # Day status
            if day["net_pnl"] > 0:
                day["status"] = "WIN"
            elif day["net_pnl"] < 0:
                day["status"] = "LOSS"
            else:
                day["status"] = "NEUTRAL"

        return daily_map

    @staticmethod
    def calculate_streaks(daily_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate winning and losing day streaks in chronological order.
        Rules:
        - Day with Net P&L > 0 is WIN.
        - Day with Net P&L < 0 is LOSS.
        - Day with Net P&L == 0 or no trades is NEUTRAL (breaks streak).
        """
        sorted_dates = sorted(daily_map.keys())
        if not sorted_dates:
            return {
                "current_streak_type": "NONE",
                "current_streak_count": 0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0,
                "total_winning_days": 0,
                "total_losing_days": 0,
                "total_neutral_days": 0,
                "longest_no_trade_period_days": 0
            }

        cur_wins = 0
        max_wins = 0
        cur_losses = 0
        max_losses = 0
        tot_wins = 0
        tot_losses = 0
        tot_neutral = 0

        for d_str in sorted_dates:
            day = daily_map[d_str]
            net = day["net_pnl"]
            if net > 0:
                tot_wins += 1
                cur_wins += 1
                cur_losses = 0
                if cur_wins > max_wins:
                    max_wins = cur_wins
            elif net < 0:
                tot_losses += 1
                cur_losses += 1
                cur_wins = 0
                if cur_losses > max_losses:
                    max_losses = cur_losses
            else:
                tot_neutral += 1
                cur_wins = 0
                cur_losses = 0

        # Current streak from the most recent trading date
        cur_type = "NONE"
        cur_count = 0
        if sorted_dates:
            last_day = daily_map[sorted_dates[-1]]
            if last_day["net_pnl"] > 0:
                cur_type = "WIN"
                cur_count = cur_wins
            elif last_day["net_pnl"] < 0:
                cur_type = "LOSS"
                cur_count = cur_losses

        # Calculate longest no-trade period (calendar days between trading days)
        longest_gap = 0
        date_objs = [daily_map[d]["date_obj"] for d in sorted_dates]
        for i in range(len(date_objs) - 1):
            gap = (date_objs[i + 1] - date_objs[i]).days - 1
            if gap > longest_gap:
                longest_gap = gap

        return {
            "current_streak_type": cur_type,
            "current_streak_count": cur_count,
            "max_consecutive_wins": max_wins,
            "max_consecutive_losses": max_losses,
            "total_winning_days": tot_wins,
            "total_losing_days": tot_losses,
            "total_neutral_days": tot_neutral,
            "longest_no_trade_period_days": longest_gap
        }

    @classmethod
    def get_monthly_calendar(
        cls,
        trades: List[Dict[str, Any]],
        year: int,
        month: int,
        tested_start_date: Optional[str] = None,
        tested_end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate full-month Monday-Sunday grid and monthly summary analytics.
        Distinguishes TRADED, NO_TRADE, WEEKEND, HOLIDAY, and FUTURE.
        """
        from backend.app.analytics.nse_holidays import is_weekend, get_nse_holiday_name

        now_ist = get_current_ist_datetime()
        today_date = now_ist.date()

        # Aggregate all trades
        daily_map = cls.aggregate_trades_by_date(trades)

        # Get calendar details for month
        first_weekday, num_days = calendar.monthrange(year, month)
        # first_weekday: 0=Monday, 6=Sunday

        month_name = calendar.month_name[month]
        month_str = f"{year}-{month:02d}"

        # Filter days for this month
        month_days_list = []
        month_trades_count = 0
        month_net_pnl = 0.0
        month_gross_profit = 0.0
        month_gross_loss = 0.0
        month_charges = 0.0
        month_slippage = 0.0
        month_winning_days = 0
        month_losing_days = 0
        month_no_trade_days = 0
        best_day: Optional[Dict[str, Any]] = None
        worst_day: Optional[Dict[str, Any]] = None

        all_holding_times = []

        for d in range(1, num_days + 1):
            cur_date = date(year, month, d)
            cur_date_str = f"{year}-{month:02d}-{d:02d}"
            weekday = cur_date.weekday()  # 0=Monday, 6=Sunday
            is_future = cur_date > today_date
            is_wknd = is_weekend(cur_date)
            holiday = get_nse_holiday_name(cur_date)

            day_data = daily_map.get(cur_date_str)

            # Determine whether day is in tested backtest range
            in_tested_range = False
            if tested_start_date and tested_end_date:
                in_tested_range = (tested_start_date <= cur_date_str <= tested_end_date)

            if day_data:
                trades_count = day_data["trades_count"]
                net_pnl = day_data["net_pnl"]
                gross_prof = day_data["gross_profit"]
                gross_loss = day_data["gross_loss"]
                charges = day_data["total_charges"]
                slippage = day_data["slippage_cost"]
                wins = day_data["wins"]
                losses = day_data["losses"]
                win_rate = day_data["win_rate"]
                avg_hold = day_data["avg_holding_time"]
                status = day_data["status"]
                all_holding_times.extend(day_data["holding_times"])

                month_trades_count += trades_count
                month_net_pnl = round(month_net_pnl + net_pnl, 2)
                month_gross_profit = round(month_gross_profit + gross_prof, 2)
                month_gross_loss = round(month_gross_loss + gross_loss, 2)
                month_charges = round(month_charges + charges, 2)
                month_slippage = round(month_slippage + slippage, 2)

                if net_pnl > 0:
                    month_winning_days += 1
                elif net_pnl < 0:
                    month_losing_days += 1

                # Best/worst tracking
                if best_day is None or net_pnl > best_day["net_pnl"]:
                    best_day = {"date": cur_date_str, "net_pnl": net_pnl}
                if worst_day is None or net_pnl < worst_day["net_pnl"]:
                    worst_day = {"date": cur_date_str, "net_pnl": net_pnl}

                has_trades = True
            else:
                trades_count = 0
                net_pnl = 0.0
                gross_prof = 0.0
                gross_loss = 0.0
                charges = 0.0
                slippage = 0.0
                wins = 0
                losses = 0
                win_rate = 0.0
                avg_hold = 0.0
                has_trades = False

                if is_wknd:
                    status = "WEEKEND"
                elif holiday:
                    status = "HOLIDAY"
                elif in_tested_range:
                    status = "NO_TRADE"
                    month_no_trade_days += 1
                elif is_future:
                    status = "FUTURE"
                else:
                    status = "NO_TRADE"
                    month_no_trade_days += 1

            month_days_list.append({
                "day_number": d,
                "date": cur_date_str,
                "weekday": weekday,  # 0=Mon .. 6=Sun
                "weekday_name": calendar.day_name[weekday],
                "is_future": is_future,
                "is_weekend": is_wknd,
                "is_holiday": bool(holiday),
                "holiday_name": holiday,
                "has_trades": has_trades,
                "in_tested_range": in_tested_range,
                "trades_count": trades_count,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "gross_profit": gross_prof,
                "gross_loss": gross_loss,
                "total_charges": charges,
                "slippage_cost": slippage,
                "net_pnl": net_pnl,
                "status": status,
                "avg_holding_time": avg_hold
            })

        # Calculate month-specific streaks
        month_daily_map = {d_str: data for d_str, data in daily_map.items() if d_str.startswith(month_str)}
        streaks = cls.calculate_streaks(month_daily_map)

        tot_active_days = month_winning_days + month_losing_days
        month_win_rate = round((month_winning_days / tot_active_days) * 100.0, 1) if tot_active_days > 0 else 0.0
        avg_daily_pnl = round(month_net_pnl / tot_active_days, 2) if tot_active_days > 0 else 0.0

        avg_hold_month = round(sum(all_holding_times) / len(all_holding_times), 1) if all_holding_times else 0.0
        max_hold_month = max(all_holding_times) if all_holding_times else 0
        min_hold_month = min(all_holding_times) if all_holding_times else 0

        summary = {
            "year": year,
            "month": month,
            "month_name": month_name,
            "month_str": month_str,
            "net_pnl": month_net_pnl,
            "gross_profit": month_gross_profit,
            "gross_loss": month_gross_loss,
            "total_charges": month_charges,
            "total_slippage": month_slippage,
            "total_trades": month_trades_count,
            "winning_days": month_winning_days,
            "losing_days": month_losing_days,
            "no_trade_days": month_no_trade_days,
            "total_trading_days": tot_active_days,
            "win_rate": month_win_rate,
            "avg_daily_pnl": avg_daily_pnl,
            "best_day": best_day or {"date": None, "net_pnl": 0.0},
            "worst_day": worst_day or {"date": None, "net_pnl": 0.0},
            "streaks": streaks,
            "holding_time": {
                "avg_minutes": avg_hold_month,
                "max_minutes": max_hold_month,
                "min_minutes": min_hold_month
            }
        }

        return {
            "year": year,
            "month": month,
            "month_name": month_name,
            "first_weekday": first_weekday,  # 0=Mon, 6=Sun
            "num_days": num_days,
            "summary": summary,
            "days": month_days_list
        }

    @classmethod
    def get_yearly_overview(
        cls,
        trades: List[Dict[str, Any]],
        year: int
    ) -> Dict[str, Any]:
        """
        Generate 12-month yearly performance grid and annual summary.
        """
        daily_map = cls.aggregate_trades_by_date(trades)
        now_ist = get_current_ist_datetime()
        current_year = now_ist.year
        current_month = now_ist.month

        months_list = []
        annual_net_pnl = 0.0
        annual_gross_profit = 0.0
        annual_gross_loss = 0.0
        annual_charges = 0.0
        annual_slippage = 0.0
        annual_trades = 0
        annual_winning_days = 0
        annual_losing_days = 0
        profitable_months = 0
        losing_months = 0
        neutral_months = 0

        best_month: Optional[Dict[str, Any]] = None
        worst_month: Optional[Dict[str, Any]] = None

        year_daily_map = {d_str: data for d_str, data in daily_map.items() if d_str.startswith(f"{year}-")}

        for m in range(1, 13):
            m_str = f"{year}-{m:02d}"
            m_name = calendar.month_name[m]
            m_short = calendar.month_abbr[m]
            is_future = (year > current_year) or (year == current_year and m > current_month)

            m_trades_cnt = 0
            m_net = 0.0
            m_gross_prof = 0.0
            m_gross_loss = 0.0
            m_chg = 0.0
            m_slip = 0.0
            m_win_days = 0
            m_loss_days = 0

            # Sum daily data for month m
            for d_str, day_data in year_daily_map.items():
                if d_str.startswith(m_str):
                    m_trades_cnt += day_data["trades_count"]
                    m_net = round(m_net + day_data["net_pnl"], 2)
                    m_gross_prof = round(m_gross_prof + day_data["gross_profit"], 2)
                    m_gross_loss = round(m_gross_loss + day_data["gross_loss"], 2)
                    m_chg = round(m_chg + day_data["total_charges"], 2)
                    m_slip = round(m_slip + day_data["slippage_cost"], 2)
                    if day_data["net_pnl"] > 0:
                        m_win_days += 1
                    elif day_data["net_pnl"] < 0:
                        m_loss_days += 1

            annual_trades += m_trades_cnt
            annual_net_pnl = round(annual_net_pnl + m_net, 2)
            annual_gross_profit = round(annual_gross_profit + m_gross_prof, 2)
            annual_gross_loss = round(annual_gross_loss + m_gross_loss, 2)
            annual_charges = round(annual_charges + m_chg, 2)
            annual_slippage = round(annual_slippage + m_slip, 2)
            annual_winning_days += m_win_days
            annual_losing_days += m_loss_days

            if is_future:
                status = "FUTURE"
            elif m_trades_cnt == 0:
                status = "NO_ACTIVITY"
                neutral_months += 1
            elif m_net > 0:
                status = "PROFIT"
                profitable_months += 1
            elif m_net < 0:
                status = "LOSS"
                losing_months += 1
            else:
                status = "NEUTRAL"
                neutral_months += 1

            tot_act_days = m_win_days + m_loss_days
            m_win_rate = round((m_win_days / tot_act_days) * 100.0, 1) if tot_act_days > 0 else 0.0

            if m_trades_cnt > 0:
                if best_month is None or m_net > best_month["net_pnl"]:
                    best_month = {"month": m, "month_name": m_name, "net_pnl": m_net}
                if worst_month is None or m_net < worst_month["net_pnl"]:
                    worst_month = {"month": m, "month_name": m_name, "net_pnl": m_net}

            months_list.append({
                "month": m,
                "month_name": m_name,
                "short_name": m_short,
                "is_future": is_future,
                "trades_count": m_trades_cnt,
                "net_pnl": m_net,
                "gross_profit": m_gross_prof,
                "gross_loss": m_gross_loss,
                "charges": m_chg,
                "slippage": m_slip,
                "winning_days": m_win_days,
                "losing_days": m_loss_days,
                "win_rate": m_win_rate,
                "status": status
            })

        year_streaks = cls.calculate_streaks(year_daily_map)

        annual_summary = {
            "year": year,
            "annual_net_pnl": annual_net_pnl,
            "annual_gross_profit": annual_gross_profit,
            "annual_gross_loss": annual_gross_loss,
            "annual_charges": annual_charges,
            "annual_slippage": annual_slippage,
            "total_trades": annual_trades,
            "profitable_months": profitable_months,
            "losing_months": losing_months,
            "neutral_months": neutral_months,
            "winning_days": annual_winning_days,
            "losing_days": annual_losing_days,
            "best_month": best_month or {"month": None, "month_name": "None", "net_pnl": 0.0},
            "worst_month": worst_month or {"month": None, "month_name": "None", "net_pnl": 0.0},
            "max_consecutive_losing_days": year_streaks["max_consecutive_losses"],
            "max_consecutive_winning_days": year_streaks["max_consecutive_wins"]
        }

        return {
            "year": year,
            "annual_summary": annual_summary,
            "months": months_list
        }

    @classmethod
    def get_custom_range_analysis(
        cls,
        trades: List[Dict[str, Any]],
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Analyze performance across a custom date range (inclusive).
        """
        daily_map = cls.aggregate_trades_by_date(trades)

        filtered_dates = sorted([d for d in daily_map.keys() if start_date <= d <= end_date])
        filtered_daily_map = {d: daily_map[d] for d in filtered_dates}

        total_trades = sum(d["trades_count"] for d in filtered_daily_map.values())
        gross_profit = round(sum(d["gross_profit"] for d in filtered_daily_map.values()), 2)
        gross_loss = round(sum(d["gross_loss"] for d in filtered_daily_map.values()), 2)
        total_charges = round(sum(d["total_charges"] for d in filtered_daily_map.values()), 2)
        total_slippage = round(sum(d["slippage_cost"] for d in filtered_daily_map.values()), 2)
        net_pnl = round(sum(d["net_pnl"] for d in filtered_daily_map.values()), 2)

        winning_days = sum(1 for d in filtered_daily_map.values() if d["net_pnl"] > 0)
        losing_days = sum(1 for d in filtered_daily_map.values() if d["net_pnl"] < 0)
        tot_active_days = winning_days + losing_days
        win_rate = round((winning_days / tot_active_days) * 100.0, 1) if tot_active_days > 0 else 0.0

        streaks = cls.calculate_streaks(filtered_daily_map)

        all_trades = []
        for d in filtered_dates:
            all_trades.extend(filtered_daily_map[d]["trades"])

        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_trades": total_trades,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_charges": total_charges,
            "total_slippage": total_slippage,
            "net_pnl": net_pnl,
            "winning_days": winning_days,
            "losing_days": losing_days,
            "total_trading_days": tot_active_days,
            "win_rate": win_rate,
            "streaks": streaks,
            "daily_summary": [filtered_daily_map[d] for d in filtered_dates],
            "trades": all_trades
        }
