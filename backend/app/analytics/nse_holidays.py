"""
NSE / Indian Exchange Trading Calendar & Holiday Directory.
Tracks exchange holidays, weekends, and trading day validations across years (2024-2027).
"""

from datetime import date
from typing import Optional, Dict

# Official NSE Trading Holidays (excluding normal Saturday/Sunday closures)
NSE_HOLIDAYS: Dict[str, str] = {
    # 2024
    "2024-01-22": "Special Holiday (Ayodhya)",
    "2024-01-26": "Republic Day",
    "2024-03-08": "Mahashivratri",
    "2024-03-25": "Holi",
    "2024-03-29": "Good Friday",
    "2024-04-11": "Id-Ul-Fitr (Ramzan Eid)",
    "2024-04-17": "Shri Ram Navami",
    "2024-05-01": "Maharashtra Day",
    "2024-05-20": "General Parliamentary Elections",
    "2024-06-17": "Bakri Id",
    "2024-07-17": "Muharram",
    "2024-08-15": "Independence Day",
    "2024-10-02": "Mahatma Gandhi Jayanti",
    "2024-11-01": "Diwali Laxmi Pujan (Muhurat Trading)",
    "2024-11-15": "Guru Nanak Jayanti",
    "2024-11-20": "Maharashtra Assembly Election",
    "2024-12-25": "Christmas",

    # 2025
    "2025-02-26": "Mahashivratri",
    "2025-03-14": "Holi",
    "2025-03-31": "Id-Ul-Fitr",
    "2025-04-10": "Mahavir Jayanti",
    "2025-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2025-04-18": "Good Friday",
    "2025-05-01": "Maharashtra Day",
    "2025-08-15": "Independence Day",
    "2025-08-27": "Ganesh Chaturthi",
    "2025-10-02": "Mahatma Gandhi Jayanti",
    "2025-10-21": "Diwali Laxmi Pujan",
    "2025-10-22": "Diwali Balipratipada",
    "2025-11-05": "Guru Nanak Jayanti",
    "2025-12-25": "Christmas",

    # 2026
    "2026-01-26": "Republic Day",
    "2026-02-16": "Mahashivratri",
    "2026-03-03": "Holi",
    "2026-03-20": "Id-Ul-Fitr",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-27": "Bakri Id",
    "2026-08-15": "Independence Day",
    "2026-08-26": "Milad-un-Nabi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali Balipratipada",
    "2026-11-24": "Guru Nanak Jayanti",
    "2026-12-25": "Christmas",

    # 2027
    "2027-01-26": "Republic Day",
    "2027-03-08": "Mahashivratri",
    "2027-03-23": "Holi",
    "2027-03-26": "Good Friday",
    "2027-04-14": "Dr. Ambedkar Jayanti",
    "2027-05-01": "Maharashtra Day",
    "2027-08-15": "Independence Day",
    "2027-10-02": "Mahatma Gandhi Jayanti",
    "2027-10-11": "Dussehra",
    "2027-10-29": "Diwali Laxmi Pujan",
    "2027-11-15": "Guru Nanak Jayanti",
    "2027-12-25": "Christmas"
}


def get_nse_holiday_name(d: date) -> Optional[str]:
    """Return holiday name if the date is an exchange trading holiday, else None."""
    return NSE_HOLIDAYS.get(d.strftime("%Y-%m-%d"))


def is_weekend(d: date) -> bool:
    """Return True if Saturday (5) or Sunday (6)."""
    return d.weekday() >= 5


def is_trading_day(d: date) -> bool:
    """
    Return True if date is a regular exchange trading weekday (not weekend and not holiday).
    """
    if is_weekend(d):
        return False
    if get_nse_holiday_name(d) is not None:
        return False
    return True
