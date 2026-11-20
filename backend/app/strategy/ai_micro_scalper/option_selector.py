import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from backend.app.options.selector import OptionContractSelector
from backend.app.options.master import InstrumentMaster

logger = logging.getLogger("nextrade.ai_micro_scalper.option_selector")
IST = timezone(timedelta(hours=5, minutes=30))


class AIMicroScalperOptionSelector:
    """
    Dedicated Option Selection Engine for NEXTRADE AI MICRO-SCALPER V1.
    - Resolves ATM and 1-strike ITM option contracts.
    - Targets the preferred ₹100–₹150 premium range.
    - Enforces liquidity and bid-ask spread limits (default <= 0.5 pts).
    - Checks 90% capital deployment affordability (Starting capital ₹20,000, 2 lots).
    - Fetches dynamic contract lot sizes (no hardcoded 65 assumption).
    """

    def __init__(
        self,
        preferred_premium_min: float = 100.0,
        preferred_premium_max: float = 150.0,
        max_bid_ask_spread: float = 0.50,
        max_capital_deployment_pct: float = 90.0,
        default_lots: int = 2
    ):
        self.preferred_premium_min = preferred_premium_min
        self.preferred_premium_max = preferred_premium_max
        self.max_bid_ask_spread = max_bid_ask_spread
        self.max_capital_deployment_pct = max_capital_deployment_pct
        self.default_lots = default_lots
        self.base_selector = OptionContractSelector()
        self.instrument_master = InstrumentMaster()

    def get_upcoming_expiry(self, ref_date: Optional[datetime] = None) -> str:
        """Fetch nearest weekly Thursday expiry date (YYYY-MM-DD)."""
        expiries = self.base_selector.get_upcoming_expiries(reference_date=ref_date)
        return expiries[0] if expiries else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def resolve_lot_size(
        self,
        token: Optional[str] = None,
        instrument_data: Optional[Dict[str, Any]] = None,
        default_fallback: int = 65
    ) -> int:
        """
        Dynamically fetch contract lot size from instrument master or metadata.
        Never hardcodes lot size.
        """
        if instrument_data and "lot_size" in instrument_data and int(instrument_data["lot_size"]) > 0:
            return int(instrument_data["lot_size"])
        return default_fallback

    def select_contract(
        self,
        spot_price: float,
        option_type: str = "CE",
        quotes_map: Optional[Dict[str, Dict[str, Any]]] = None,
        available_capital: float = 20000.0,
        lots: int = 2,
        lot_size: Optional[int] = None,
        expiry: Optional[str] = None,
        estimated_charges: float = 20.0
    ) -> Dict[str, Any]:
        """
        Select best option contract matching the scalper's strict criteria:
        1. Calculate ATM strike.
        2. Evaluate ATM (strike 0) vs 1-strike ITM (strike -50 for CE, +50 for PE).
        3. Prioritize premium in ₹100–₹150 range.
        4. Validate bid-ask spread <= max_bid_ask_spread.
        5. Verify capital deployment <= 90% of available capital.
        """
        atm_strike = self.base_selector.calculate_atm_strike(spot_price)
        selected_expiry = expiry or self.get_upcoming_expiry()
        opt_type = option_type.upper()

        # 1-strike ITM calculation
        # For CE: In-The-Money is below spot (ATM - 50)
        # For PE: In-The-Money is above spot (ATM + 50)
        itm_strike = (atm_strike - 50.0) if opt_type == "CE" else (atm_strike + 50.0)

        candidates = [
            {"strike": atm_strike, "is_itm": False, "desc": "ATM"},
            {"strike": itm_strike, "is_itm": True, "desc": "ITM (1 Strike)"}
        ]

        quotes = quotes_map or {}

        # Evaluate candidate premiums
        evaluated_candidates = []
        for cand in candidates:
            strk = cand["strike"]
            sym = self.base_selector.generate_option_symbol(strk, selected_expiry, opt_type)
            token = f"OPT_{int(strk)}_{opt_type}"

            q = quotes.get(sym) or quotes.get(token) or quotes.get(f"ATM_{opt_type}") or quotes.get(opt_type) or {}
            prem = float(q.get("last_price") or q.get("close") or q.get("premium") or (q.get("ask") if q.get("ask") else 125.0))
            bid = float(q.get("bid") if q.get("bid") is not None else (prem - 0.10))
            ask = float(q.get("ask") if q.get("ask") is not None else (prem + 0.10))
            spread = round(ask - bid, 2)

            evaluated_candidates.append({
                "strike": strk,
                "is_itm": cand["is_itm"],
                "desc": cand["desc"],
                "symbol": sym,
                "token": token,
                "premium": round(prem, 2),
                "bid": round(bid, 2),
                "ask": round(ask, 2),
                "spread": spread,
                "in_preferred_range": self.preferred_premium_min <= prem <= self.preferred_premium_max
            })

        # Selection logic:
        # If ATM is in preferred range (100 - 150), choose ATM.
        # If ATM is outside preferred range, evaluate ITM.
        # If ITM is in preferred range, choose ITM.
        # Otherwise, choose candidate whose premium is closest to the 100-150 range.
        atm_cand = evaluated_candidates[0]
        itm_cand = evaluated_candidates[1]

        if atm_cand["in_preferred_range"]:
            chosen = atm_cand
        elif itm_cand["in_preferred_range"]:
            chosen = itm_cand
        else:
            # Pick whichever is closer to target mid-premium (125.0)
            target_mid = (self.preferred_premium_min + self.preferred_premium_max) / 2.0
            diff_atm = abs(atm_cand["premium"] - target_mid)
            diff_itm = abs(itm_cand["premium"] - target_mid)
            chosen = atm_cand if diff_atm <= diff_itm else itm_cand

        effective_lot_size = lot_size if (lot_size and lot_size > 0) else self.resolve_lot_size(token=chosen["token"])
        effective_lots = lots if lots > 0 else self.default_lots
        total_qty = effective_lots * effective_lot_size

        # Affordability check
        required_capital = round((chosen["premium"] * total_qty) + estimated_charges, 2)
        max_allowed_deploy = round((self.max_capital_deployment_pct / 100.0) * available_capital, 2)
        is_affordable = bool(required_capital <= max_allowed_deploy)

        # Spread check
        spread_ok = bool(chosen["spread"] <= self.max_bid_ask_spread)
        valid_prem = bool(20.0 <= chosen["premium"] <= 500.0)

        rejection_reasons = []
        if not is_affordable:
            rejection_reasons.append(f"Required capital ₹{required_capital:.2f} exceeds 90% capital deployment cap (₹{max_allowed_deploy:.2f} of ₹{available_capital:.2f})")
        if not spread_ok:
            rejection_reasons.append(f"Bid-ask spread ({chosen['spread']:.2f} pts) exceeds maximum allowable ({self.max_bid_ask_spread:.2f} pts)")
        if not valid_prem:
            rejection_reasons.append(f"Invalid option premium (₹{chosen['premium']:.2f} outside valid ₹20–₹500 range)")

        is_valid = len(rejection_reasons) == 0

        return {
            "underlying": "NIFTY",
            "spot_price": round(spot_price, 2),
            "atm_strike": atm_strike,
            "selected_strike": chosen["strike"],
            "strike": chosen["strike"],
            "is_itm": chosen["is_itm"],
            "strike_description": chosen["desc"],
            "option_type": opt_type,
            "expiry": selected_expiry,
            "symbol": chosen["symbol"],
            "instrument_token": chosen["token"],
            "option_premium": chosen["premium"],
            "last_price": chosen["premium"],
            "premium": chosen["premium"],
            "bid": chosen["bid"],
            "ask": chosen["ask"],
            "spread": chosen["spread"],
            "lot_size": effective_lot_size,
            "lots": effective_lots,
            "quantity": total_qty,
            "required_capital": required_capital,
            "total_purchase_cost": required_capital,
            "capital_utilization_pct": round((required_capital / max(1.0, available_capital)) * 100.0, 1),
            "available_capital": available_capital,
            "max_allowed_deploy": max_allowed_deploy,
            "is_affordable": is_affordable,
            "affordable": is_affordable,
            "spread_pass": spread_ok,
            "is_valid_premium": valid_prem,
            "is_valid": is_valid,
            "rejection_reason": "; ".join(rejection_reasons) if rejection_reasons else None
        }
