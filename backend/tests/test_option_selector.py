import pytest
from backend.app.options.selector import OptionContractSelector


def test_atm_strike_calculation():
    selector = OptionContractSelector(default_lot_size=65)

    # 50-point intervals:
    # 24524.0 -> 24500.0
    assert selector.calculate_atm_strike(24524.0) == 24500.0

    # 24526.0 -> 24550.0
    assert selector.calculate_atm_strike(24526.0) == 24550.0

    # Exact boundary 24525.0 -> rounds to 24500 or 24550
    res = selector.calculate_atm_strike(24525.0)
    assert res in [24500.0, 24550.0]

    # Higher spot: 25112.5 -> 25100.0
    assert selector.calculate_atm_strike(25112.5) == 25100.0


def test_select_atm_ce_contract():
    selector = OptionContractSelector(default_lot_size=65)
    contract = selector.select_atm_ce(spot_price=24530.0)

    assert contract["underlying"] == "NIFTY"
    assert contract["strike"] == 24550.0
    assert contract["option_type"] == "CE"
    assert contract["lot_size"] == 65
    assert "NIFTY" in contract["symbol"]
    assert "24550" in contract["symbol"]


def test_no_silent_switch_while_position_open():
    selector = OptionContractSelector(default_lot_size=65)

    # Select initial contract
    c1 = selector.select_atm_ce(spot_price=24500.0)
    assert c1["strike"] == 24500.0

    # Position is opened!
    selector.set_position_open_state(True)

    # Spot jumps to 24700 (which would normally shift ATM strike to 24700)
    c2 = selector.select_atm_ce(spot_price=24700.0)

    # Must preserve the original strike 24500 while position is open!
    assert c2["strike"] == 24500.0

    # Position is closed
    selector.set_position_open_state(False)

    # Now contract updates to new ATM
    c3 = selector.select_atm_ce(spot_price=24700.0)
    assert c3["strike"] == 24700.0
