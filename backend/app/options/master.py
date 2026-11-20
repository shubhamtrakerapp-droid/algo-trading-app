import logging
from typing import Dict, Any, Optional, List
from sqlalchemy import select
from backend.app.database import AsyncSessionLocal
from backend.app.models import Instrument

logger = logging.getLogger("nextrade.instrument_master")


class InstrumentMaster:
    """
    Manages instruments, lot sizes, tokens, and contract specifications.
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def get_instrument(self, token: str, exchange_segment: str = "nse_fo") -> Optional[Dict[str, Any]]:
        """Retrieve instrument info by token and exchange segment."""
        cache_key = f"{exchange_segment}:{token}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        async with AsyncSessionLocal() as session:
            stmt = select(Instrument).where(
                Instrument.instrument_token == token,
                Instrument.exchange_segment == exchange_segment
            )
            res = await session.execute(stmt)
            inst = res.scalar_one_or_none()
            if inst:
                data = {
                    "instrument_token": inst.instrument_token,
                    "exchange_segment": inst.exchange_segment,
                    "trading_symbol": inst.trading_symbol,
                    "underlying": inst.underlying_symbol,
                    "strike": inst.strike_price,
                    "option_type": inst.option_type,
                    "expiry": inst.expiry_date,
                    "lot_size": inst.lot_size,
                    "tick_size": inst.tick_size
                }
                self._cache[cache_key] = data
                return data

        # Default fallback for NIFTY
        return {
            "instrument_token": token,
            "exchange_segment": exchange_segment,
            "trading_symbol": f"TOKEN_{token}",
            "underlying": "NIFTY",
            "strike": 24500.0,
            "option_type": "CE",
            "expiry": "",
            "lot_size": 65,
            "tick_size": 0.05
        }

    async def save_instruments(self, instruments_data: List[Dict[str, Any]]):
        """Batch save or update instruments into database."""
        async with AsyncSessionLocal() as session:
            for item in instruments_data:
                stmt = select(Instrument).where(
                    Instrument.instrument_token == item["instrument_token"],
                    Instrument.exchange_segment == item["exchange_segment"]
                )
                res = await session.execute(stmt)
                inst = res.scalar_one_or_none()
                if not inst:
                    inst = Instrument(
                        instrument_token=item["instrument_token"],
                        exchange_segment=item["exchange_segment"],
                        trading_symbol=item["trading_symbol"],
                        instrument_name=item.get("instrument_name"),
                        underlying_symbol=item.get("underlying_symbol", "NIFTY"),
                        strike_price=item.get("strike_price"),
                        option_type=item.get("option_type"),
                        expiry_date=item.get("expiry_date"),
                        lot_size=item.get("lot_size", 65),
                        tick_size=item.get("tick_size", 0.05),
                        is_active=True
                    )
                    session.add(inst)
            await session.commit()
