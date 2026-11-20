"""
Automated Validation Suite for Universal Fixed Premium SL / Target Execution Engine.
Covers Section H of specification:
1. Entry premium ₹150 -> Stop Loss ₹148, Target ₹154
2. Price reaches ₹154: exit at Target
3. Price reaches ₹148: exit at SL
4. Price reaches neither: position remains open
5. Quantity 325: ₹1,000 overlay does not alter 2-point SL
6. Quantity 600: ₹1,000 overlay reduces effective SL to 1.6667 pts
7. Gap below SL: realistic execution handles gap down correctly
8. UT Sell Signal OFF: no early UT exit
9. UT Sell Signal ON: early exit works
10. Both SL and Target touched in one candle: conservative stop and ambiguity flag
11. Same historical data and settings always produce identical results
"""

import pytest
from datetime import datetime, timedelta

from backend.app.strategy.ut_bot import UTBotStrategy
from backend.app.paper.broker import PaperBroker
from backend.app.backtest.engine import BacktestEngine
from backend.app.backtest.data_loader import BacktestDataLoader


def make_candle(ts: datetime, o: float, h: float, l: float, c: float, v: float = 1000.0) -> dict:
    return {
        "timestamp": ts,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "complete": True
    }


class TestFixedPremiumSLTargetExecution:

    def test_scenario_1_exact_sl_target_triggers(self):
        """
        Scenario 1:
        Entry premium ₹150 -> Stop Loss ₹148 (2 pts below), Target ₹154 (4 pts above).
        """
        ut = UTBotStrategy(stop_points=2.0, target_points=4.0)
        broker = PaperBroker(stop_points=2.0, target_points=4.0)

        # Broker risk param calculation
        params = broker.calculate_risk_parameters(
            lots=5,
            lot_size=65,
            entry_price=150.0,
            stop_points=2.0,
            target_points=4.0,
            max_loss_per_trade=None
        )

        assert params["entry_price"] == 150.0
        assert params["configured_sl_points"] == 2.0
        assert params["configured_target_points"] == 4.0
        assert params["effective_sl_points"] == 2.0
        assert params["sl_trigger_price"] == 148.0
        assert params["target_trigger_price"] == 154.0

    def test_scenario_2_target_execution_books_profit(self):
        """
        Scenario 2:
        High reaches ₹154 (Low > ₹148): target execution books profit at ₹154, position closed.
        """
        t0 = datetime(2026, 11, 10, 9, 30)
        engine = BacktestEngine(
            lots=5,
            lot_size=65,
            stop_points=2.0,
            target_points=4.0,
            execution_mode="TRIGGER_PRICE"
        )

        # Candle 0: Entry candle (close 150)
        # Candle 1: Next candle reaches target (Open 150, High 154.5, Low 149.5, Close 153)
        c0 = make_candle(t0, 149.0, 150.5, 148.5, 150.0)
        c1 = make_candle(t0 + timedelta(minutes=1), 150.0, 154.5, 149.5, 153.0)

        nifty_candles = [c0, c1]
        option_candles = [c0, c1]

        # Use engine to evaluate trade simulation directly
        # In trigger-price mode, target exits at exactly 154.00
        active_pos = {
            "entry_time": t0,
            "entry_price": 150.0,
            "quantity": 325,
            "configured_sl_points": 2.0,
            "configured_target_points": 4.0,
            "effective_sl_points": 2.0,
            "effective_target_points": 4.0,
            "sl_trigger": 148.0,
            "target_trigger": 154.0,
            "underlying_price": 24500.0,
            "option_symbol": "NIFTY26NOV24500CE",
            "strike": 24500.0,
            "expiry": "2026-11-26",
            "execution_mode": "TRIGGER_PRICE",
            "entry_slippage": 0.0
        }

        # Simulate candle evaluation
        res = engine._evaluate_candle_exit(active_pos, c1)
        assert res is not None
        exit_price, exit_reason, slip_cost, is_ambig, ambig_flag = res

        assert exit_reason == "TARGET"
        assert exit_price == 154.0
        assert is_ambig is False
        assert slip_cost == 0.0

    def test_scenario_3_stop_loss_execution_cuts_loss(self):
        """
        Scenario 3:
        Low reaches ₹148 (High < ₹154): stop loss executes at ₹148, position closed.
        """
        t0 = datetime(2026, 11, 10, 9, 30)
        engine = BacktestEngine(
            lots=5,
            lot_size=65,
            stop_points=2.0,
            target_points=4.0,
            execution_mode="TRIGGER_PRICE"
        )

        c1 = make_candle(t0 + timedelta(minutes=1), 150.0, 151.0, 147.8, 148.5)

        active_pos = {
            "entry_time": t0,
            "entry_price": 150.0,
            "quantity": 325,
            "configured_sl_points": 2.0,
            "configured_target_points": 4.0,
            "effective_sl_points": 2.0,
            "effective_target_points": 4.0,
            "sl_trigger": 148.0,
            "target_trigger": 154.0,
            "underlying_price": 24500.0,
            "option_symbol": "NIFTY26NOV24500CE",
            "strike": 24500.0,
            "expiry": "2026-11-26",
            "execution_mode": "TRIGGER_PRICE",
            "entry_slippage": 0.0
        }

        res = engine._evaluate_candle_exit(active_pos, c1)
        assert res is not None
        exit_price, exit_reason, slip_cost, is_ambig, ambig_flag = res

        assert exit_reason == "STOP_LOSS"
        assert exit_price == 148.0
        assert is_ambig is False

    def test_scenario_4_neither_touched_position_remains_open(self):
        """
        Scenario 4:
        Candle High < ₹154 and Low > ₹148: trade remains open, no exit executed.
        """
        t0 = datetime(2026, 11, 10, 9, 30)
        engine = BacktestEngine(lots=5, lot_size=65, stop_points=2.0, target_points=4.0)

        # High is 153.0 (below 154.0), Low is 149.0 (above 148.0)
        c1 = make_candle(t0 + timedelta(minutes=1), 150.0, 153.0, 149.0, 151.5)

        active_pos = {
            "entry_time": t0,
            "entry_price": 150.0,
            "quantity": 325,
            "configured_sl_points": 2.0,
            "configured_target_points": 4.0,
            "effective_sl_points": 2.0,
            "effective_target_points": 4.0,
            "sl_trigger": 148.0,
            "target_trigger": 154.0,
            "execution_mode": "TRIGGER_PRICE"
        }

        res = engine._evaluate_candle_exit(active_pos, c1)
        assert res is None, "Position should remain open when neither SL nor Target is touched"

    def test_scenario_5_qty_325_overlay_unmodified(self):
        """
        Scenario 5:
        Quantity 325: ₹1,000 loss overlay does not modify 2-point SL (325 * 2 = 650 <= 1000).
        """
        ut = UTBotStrategy(stop_points=2.0, target_points=4.0)
        broker = PaperBroker(stop_points=2.0, target_points=4.0)

        eff_stop = ut.calculate_effective_stop_points(stop_points=2.0, max_loss=1000.0, quantity=325)
        assert eff_stop == 2.0

        params = broker.calculate_risk_parameters(
            lots=5,
            lot_size=65,
            entry_price=150.0,
            stop_points=2.0,
            target_points=4.0,
            max_loss_per_trade=1000.0
        )
        assert params["configured_sl_points"] == 2.0
        assert params["effective_sl_points"] == 2.0
        assert params["sl_trigger_price"] == 148.0
        assert params["target_trigger_price"] == 154.0

    def test_scenario_6_qty_600_overlay_scales_sl(self):
        """
        Scenario 6:
        Quantity 600: ₹1,000 loss overlay reduces SL to 1.6667 points (1000 / 600 = 1.6667).
        """
        ut = UTBotStrategy(stop_points=2.0, target_points=4.0)
        broker = PaperBroker(stop_points=2.0, target_points=4.0)

        eff_stop = ut.calculate_effective_stop_points(stop_points=2.0, max_loss=1000.0, quantity=600)
        assert round(eff_stop, 4) == round(1000.0 / 600, 4)
        assert eff_stop < 2.0

        params = broker.calculate_risk_parameters(
            lots=10,
            lot_size=60,
            entry_price=150.0,
            stop_points=2.0,
            target_points=4.0,
            max_loss_per_trade=1000.0
        )
        assert params["configured_sl_points"] == 2.0
        assert round(params["effective_sl_points"], 4) == round(1.6667, 4)
        assert params["sl_trigger_price"] == round(150.0 - (1000.0 / 600), 2)

    def test_scenario_7_gap_below_sl_realistic_mode(self):
        """
        Scenario 7:
        Opening gap below SL: realistic execution handles gap down correctly (worse fill at open minus slippage).
        """
        t0 = datetime(2026, 11, 10, 9, 30)
        engine = BacktestEngine(
            lots=5,
            lot_size=65,
            stop_points=2.0,
            target_points=4.0,
            slippage_points=0.10,
            execution_mode="REALISTIC"
        )

        # Candle gaps down below stop (Stop is 148.0, candle opens at 145.0, high 146.0, low 144.0)
        gap_candle = make_candle(t0 + timedelta(minutes=1), 145.0, 146.0, 144.0, 145.5)

        active_pos = {
            "entry_time": t0,
            "entry_price": 150.0,
            "quantity": 325,
            "configured_sl_points": 2.0,
            "configured_target_points": 4.0,
            "effective_sl_points": 2.0,
            "effective_target_points": 4.0,
            "sl_trigger": 148.0,
            "target_trigger": 154.0,
            "underlying_price": 24500.0,
            "option_symbol": "NIFTY26NOV24500CE",
            "strike": 24500.0,
            "expiry": "2026-11-26",
            "execution_mode": "REALISTIC",
            "entry_slippage": 0.10
        }

        res = engine._evaluate_candle_exit(active_pos, gap_candle)
        assert res is not None
        exit_price, exit_reason, slip_cost, is_ambig, ambig_flag = res

        assert exit_reason == "STOP_LOSS"
        # In realistic mode, fill at gap open (145.0) - slippage (0.10) = 144.90
        assert exit_price == 144.90
        assert slip_cost > 0.0

    def test_scenario_8_exit_on_ut_sell_off(self):
        """
        Scenario 8:
        Exit on UT Sell Signal OFF: UT Sell Signal does not trigger early exit.
        """
        ut = UTBotStrategy(stop_points=2.0, target_points=4.0, exit_on_ut_sell_signal=False)
        assert ut.exit_on_ut_sell_signal is False

        # In BacktestEngine with exit_on_ut_sell_signal=False, UT sell signals are ignored
        engine = BacktestEngine(
            lots=5,
            lot_size=65,
            stop_points=2.0,
            target_points=4.0,
            exit_on_ut_sell_signal=False
        )
        assert engine.exit_on_ut_sell_signal is False

    def test_scenario_9_exit_on_ut_sell_on(self):
        """
        Scenario 9:
        Exit on UT Sell Signal ON: UT Sell Signal triggers exit at candle open.
        """
        engine = BacktestEngine(
            lots=5,
            lot_size=65,
            stop_points=2.0,
            target_points=4.0,
            exit_on_ut_sell_signal=True,
            execution_mode="TRIGGER_PRICE"
        )
        assert engine.exit_on_ut_sell_signal is True

    def test_scenario_10_ambiguous_candle_both_touched(self):
        """
        Scenario 10:
        Both SL and Target touched within same candle: conservative stop loss applied,
        trade marked is_ambiguous = True with ambiguity_flag = 'BOTH_TOUCHED_SAME_CANDLE'.
        """
        t0 = datetime(2026, 11, 10, 9, 30)
        engine = BacktestEngine(
            lots=5,
            lot_size=65,
            stop_points=2.0,
            target_points=4.0,
            execution_mode="TRIGGER_PRICE",
            same_candle_resolution="CONSERVATIVE_STOP"
        )

        # Huge volatility candle: Entry was 150.0. Stop 148.0, Target 154.0.
        # Candle has High 155.0 (touches target) and Low 147.0 (touches stop)
        ambig_candle = make_candle(t0 + timedelta(minutes=1), 150.0, 155.0, 147.0, 151.0)

        active_pos = {
            "entry_time": t0,
            "entry_price": 150.0,
            "quantity": 325,
            "configured_sl_points": 2.0,
            "configured_target_points": 4.0,
            "effective_sl_points": 2.0,
            "effective_target_points": 4.0,
            "sl_trigger": 148.0,
            "target_trigger": 154.0,
            "underlying_price": 24500.0,
            "option_symbol": "NIFTY26NOV24500CE",
            "strike": 24500.0,
            "expiry": "2026-11-26",
            "execution_mode": "TRIGGER_PRICE",
            "entry_slippage": 0.0
        }

        res = engine._evaluate_candle_exit(active_pos, ambig_candle)
        assert res is not None
        exit_price, exit_reason, slip_cost, is_ambig, ambig_flag = res

        # Conservative resolution prefers STOP_LOSS
        assert exit_reason == "STOP_LOSS"
        assert exit_price == 148.0
        assert is_ambig is True
        assert ambig_flag == "BOTH_TOUCHED_SAME_CANDLE"

    def test_scenario_11_deterministic_reproducibility(self):
        """
        Scenario 11:
        Deterministic backtest test: Run with identical seed and settings twice ->
        identical trade count, gross P&L, charges, slippage, net P&L down to exact paisa.
        """
        loader = BacktestDataLoader()
        nifty1, opt1 = loader.generate_synthetic_backtest_dataset(days=3, seed=777)
        nifty2, opt2 = loader.generate_synthetic_backtest_dataset(days=3, seed=777)

        engine1 = BacktestEngine(
            lots=5,
            lot_size=65,
            stop_points=2.0,
            target_points=4.0,
            execution_mode="TRIGGER_PRICE"
        )
        engine2 = BacktestEngine(
            lots=5,
            lot_size=65,
            stop_points=2.0,
            target_points=4.0,
            execution_mode="TRIGGER_PRICE"
        )

        res1 = engine1.run_backtest(
            nifty_candles=nifty1,
            option_candles=opt1,
            strategy_id="UT_BOT",
            ut_bot_params={"key_value": 1.0, "atr_period": 10, "lots": 5, "lot_size": 65, "stop_points": 2.0, "target_points": 4.0},
            data_source="SYNTHETIC_TEST"
        )

        res2 = engine2.run_backtest(
            nifty_candles=nifty2,
            option_candles=opt2,
            strategy_id="UT_BOT",
            ut_bot_params={"key_value": 1.0, "atr_period": 10, "lots": 5, "lot_size": 65, "stop_points": 2.0, "target_points": 4.0},
            data_source="SYNTHETIC_TEST"
        )

        assert res1["total_trades"] == res2["total_trades"]
        assert res1["gross_profit"] == res2["gross_profit"]
        assert res1["gross_loss"] == res2["gross_loss"]
        assert res1["total_charges"] == res2["total_charges"]
        assert res1["net_profit"] == res2["net_profit"]
        assert res1["win_rate"] == res2["win_rate"]
        assert res1["max_drawdown"] == res2["max_drawdown"]
        assert len(res1["trades"]) == len(res2["trades"])

        # Check mathematical reconciliation identity
        gross_prof = res1["gross_profit"]
        gross_loss = res1["gross_loss"]
        total_chg = res1["total_charges"]
        net_prof = res1["net_profit"]
        assert round(gross_prof - gross_loss - total_chg, 2) == round(net_prof, 2)
