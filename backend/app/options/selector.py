import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any

logger = logging.getLogger("nextrade.options_selector")


class OptionContractSelector:
    """
    NIFTY ATM CE Option Contract Selector and Expiry Manager.
    Adheres strictly to NSE contract specifications and Kotak Neo instrument identifiers.
    """

    def __init__(self, default_lot_size: int = 65):
        self.underlying = "NIFTY"
        self.strike_interval = 50.0  # NIFTY strike interval is 50 points
        self.default_lot_size = default_lot_size
        self._manual_override: Optional[Dict[str, Any]] = None
        self._active_contract: Optional[Dict[str, Any]] = None
        self._is_position_open = False

    def set_position_open_state(self, is_open: bool):
        """Record whether a paper trading position is open to prevent silent contract switching."""
        self._is_position_open = is_open

    def get_upcoming_expiries(self, reference_date: Optional[datetime] = None) -> List[str]:
        """
        Generate upcoming NSE weekly/monthly Thursday expiry dates.
        NSE NIFTY weekly/monthly options expire on Thursdays.
        Format: YYYY-MM-DD
        """
        ref = reference_date or datetime.now(timezone.utc)
        expiries = []
        # Look ahead 6 weeks
        current = ref
        for _ in range(45):
            # Thursday is weekday 3 (Monday is 0)
            if current.weekday() == 3:
                expiries.append(current.strftime("%Y-%m-%d"))
                if len(expiries) >= 5:
                    break
            current += timedelta(days=1)

        return expiries

    def calculate_atm_strike(self, spot_price: float) -> float:
        """
        Calculate ATM strike price using standard 50-point intervals.
        e.g., 24524.80 -> 24500.0, 24526.00 -> 24550.0
        """
        if spot_price <= 0:
            return 24500.0
        return round(spot_price / self.strike_interval) * self.strike_interval

    def generate_option_symbol(self, strike: float, expiry_str: str, option_type: str = "CE") -> str:
        """
        Generate standard NSE trading symbol format.
        e.g. NIFTY 24550 CE (Expiry: 2026-11-26 -> NIFTY 26NOV 24550 CE)
        """
        try:
            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
            # Format: NIFTY DDMMMYY STRIKE CE e.g. NIFTY26NOV24550CE
            formatted_date = dt.strftime("%d%b%y").upper()
            return f"NIFTY{formatted_date}{int(strike)}{option_type}"
        except Exception:
            return f"NIFTY {int(strike)} {option_type}"

    def select_atm_ce(
        self,
        spot_price: float,
        expiry: Optional[str] = None,
        manual_token: Optional[str] = None,
        manual_strike: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Identify and select ATM CE option contract.
        If a position is already open and no manual override is forced,
        preserves the current active contract to prevent silent contract switching.
        """
        # If manual override is requested
        if manual_strike and manual_strike > 0:
            exp = expiry or self.get_upcoming_expiries()[0]
            sym = self.generate_option_symbol(manual_strike, exp, "CE")
            contract = {
                "underlying": self.underlying,
                "spot_price": spot_price,
                "strike": float(manual_strike),
                "option_type": "CE",
                "expiry": exp,
                "symbol": sym,
                "instrument_token": manual_token or f"OPT_{int(manual_strike)}_CE",
                "lot_size": self.default_lot_size,
                "is_manual": True
            }
            self._active_contract = contract
            return contract

        # If a paper position is already active, keep existing contract to avoid silent contract switches
        if self._is_position_open and self._active_contract is not None:
            # Update spot price only
            contract = dict(self._active_contract)
            contract["spot_price"] = spot_price
            return contract

        # Calculate standard ATM strike
        atm_strike = self.calculate_atm_strike(spot_price)
        expiries = self.get_upcoming_expiries()
        selected_expiry = expiry if expiry and expiry in expiries else expiries[0]
        sym = self.generate_option_symbol(atm_strike, selected_expiry, "CE")

        # In production with Kotak Neo master data, instrument_token comes from scrip master.
        # In synthetic / demo mode, deterministic token is OPT_<strike>_CE.
        token = f"OPT_{int(atm_strike)}_CE"

        contract = {
            "underlying": self.underlying,
            "spot_price": spot_price,
            "strike": atm_strike,
            "option_type": "CE",
            "expiry": selected_expiry,
            "symbol": sym,
            "instrument_token": token,
            "lot_size": self.default_lot_size,
            "is_manual": False
        }
        self._active_contract = contract
        return contract

    def select_atm_pe(
        self,
        spot_price: float,
        expiry: Optional[str] = None,
        manual_token: Optional[str] = None,
        manual_strike: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Identify and select ATM PE option contract.
        If a position is already open for PE, preserves the active contract.
        """
        if manual_strike and manual_strike > 0:
            exp = expiry or self.get_upcoming_expiries()[0]
            sym = self.generate_option_symbol(manual_strike, exp, "PE")
            contract = {
                "underlying": self.underlying,
                "spot_price": spot_price,
                "strike": float(manual_strike),
                "option_type": "PE",
                "expiry": exp,
                "symbol": sym,
                "instrument_token": manual_token or f"OPT_{int(manual_strike)}_PE",
                "lot_size": self.default_lot_size,
                "is_manual": True
            }
            self._active_contract = contract
            return contract

        if self._is_position_open and self._active_contract is not None and self._active_contract.get("option_type") == "PE":
            contract = dict(self._active_contract)
            contract["spot_price"] = spot_price
            return contract

        atm_strike = self.calculate_atm_strike(spot_price)
        expiries = self.get_upcoming_expiries()
        selected_expiry = expiry if expiry and expiry in expiries else expiries[0]
        sym = self.generate_option_symbol(atm_strike, selected_expiry, "PE")
        token = f"OPT_{int(atm_strike)}_PE"

        contract = {
            "underlying": self.underlying,
            "spot_price": spot_price,
            "strike": atm_strike,
            "option_type": "PE",
            "expiry": selected_expiry,
            "symbol": sym,
            "instrument_token": token,
            "lot_size": self.default_lot_size,
            "is_manual": False
        }
        self._active_contract = contract
        return contract

    def select_atm_contract(
        self,
        spot_price: float,
        option_type: str = "CE",
        expiry: Optional[str] = None,
        manual_token: Optional[str] = None,
        manual_strike: Optional[float] = None
    ) -> Dict[str, Any]:
        """Unified method to select either ATM CE or ATM PE."""
        if option_type.upper() == "PE":
            return self.select_atm_pe(spot_price, expiry, manual_token, manual_strike)
        return self.select_atm_ce(spot_price, expiry, manual_token, manual_strike)

    def get_option_chain_strikes(self, spot_price: float, count: int = 10) -> List[Dict[str, Any]]:
        """
        Generate a list of strike rows centered around ATM for the Option Chain view.
        """
        atm = self.calculate_atm_strike(spot_price)
        half = count // 2
        strikes = []
        for i in range(-half, half + 1):
            s = atm + (i * self.strike_interval)
            # Calculate theoretical CE/PE values based on moneyness for display
            ce_intrinsic = max(0.0, spot_price - s)
            pe_intrinsic = max(0.0, s - spot_price)
            ce_time_val = max(10.0, 120.0 - abs(spot_price - s) * 0.12)
            pe_time_val = max(10.0, 120.0 - abs(spot_price - s) * 0.12)

            strikes.append({
                "strike": s,
                "is_atm": (s == atm),
                "ce_symbol": f"NIFTY {int(s)} CE",
                "ce_token": f"OPT_{int(s)}_CE",
                "ce_ltp": round(ce_intrinsic + ce_time_val, 2),
                "ce_oi": int(80000 + random_offset(s, 20000)),
                "ce_volume": int(45000 + random_offset(s, 15000)),
                "pe_symbol": f"NIFTY {int(s)} PE",
                "pe_token": f"OPT_{int(s)}_PE",
                "pe_ltp": round(pe_intrinsic + pe_time_val, 2),
                "pe_oi": int(75000 + random_offset(s, 18000)),
                "pe_volume": int(40000 + random_offset(s, 12000)),
            })
        return strikes


def random_offset(seed: float, scale: float) -> float:
    # Deterministic pseudo-random offset based on strike
    return (int(seed * 17) % int(scale))
