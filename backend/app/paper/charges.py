from dataclasses import dataclass
from typing import Optional


@dataclass
class TransactionCharges:
    entry_charge: float
    exit_charge: float
    total_charges: float
    entry_order_count: int = 1
    exit_order_count: int = 1
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_txn_charge: float = 0.0
    gst: float = 0.0
    sebi_charge: float = 0.0
    stamp_duty: float = 0.0


class ChargesCalculator:
    """
    Authoritative Paper Trading Charges Calculator for NEXTRADE.

    FLAT PER-ORDER CHARGES:
    - Entry order charge: Default ₹10 per executed entry order.
    - Exit order charge: Default ₹10 per executed exit order.
    - Total round-trip charges for 1 entry + 1 exit: ₹20.

    CRITICAL RULE:
    Charges are NEVER multiplied by quantity, lots, lot size, premium price, or turnover.
    Multiple partial fills of the same order count as 1 order charge.
    """

    def __init__(
        self,
        entry_charge_per_order: float = 10.0,
        exit_charge_per_order: float = 10.0,
    ):
        self.entry_charge_per_order = float(entry_charge_per_order)
        self.exit_charge_per_order = float(exit_charge_per_order)

    def calculate_charges(
        self,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        quantity: int = 0,
        entry_order_count: int = 1,
        exit_order_count: int = 1,
        entry_charge_override: Optional[float] = None,
        exit_charge_override: Optional[float] = None,
    ) -> TransactionCharges:
        """
        Calculate total round-trip charges:
        entryCharges = entryOrderCount * entryChargePerOrder
        exitCharges = exitOrderCount * exitChargePerOrder
        totalCharges = entryCharges + exitCharges
        """
        entry_rate = float(
            entry_charge_override if entry_charge_override is not None else self.entry_charge_per_order
        )
        exit_rate = float(
            exit_charge_override if exit_charge_override is not None else self.exit_charge_per_order
        )

        entry_charges = round(entry_order_count * entry_rate, 2)
        exit_charges = round(exit_order_count * exit_rate, 2)
        total_charges = round(entry_charges + exit_charges, 2)

        return TransactionCharges(
            entry_charge=entry_charges,
            exit_charge=exit_charges,
            total_charges=total_charges,
            entry_order_count=entry_order_count,
            exit_order_count=exit_order_count,
            brokerage=total_charges,
            stt=0.0,
            exchange_txn_charge=0.0,
            gst=0.0,
            sebi_charge=0.0,
            stamp_duty=0.0,
        )
