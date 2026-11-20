import asyncio
import json
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.coordinator import coordinator
from backend.app.adapters.base import MarketTickData, CandleData
from backend.app.adapters.kotak_neo import KotakNeoAdapter, is_market_hours


@pytest.mark.asyncio
async def test_kotak_neo_adapter_sfeed_structure():
    """Verify KotakNeoAdapter SFeed integration methods and state transitions."""
    adapter = KotakNeoAdapter()
    assert hasattr(adapter, "subscribe_tokens") or hasattr(adapter, "subscribed_tokens")
    assert adapter.connection_state == "DISCONNECTED"

    # Test state setter
    adapter.set_connection_state("CONNECTING", "Testing connecting state")
    assert adapter.connection_state == "CONNECTING"
    assert adapter.is_connected is False

    adapter.set_connection_state("CONNECTED", "Testing connected state")
    assert adapter.connection_state == "CONNECTED"
    assert adapter.is_connected is True

    adapter.set_connection_state("MARKET CLOSED", "Market is closed")
    assert adapter.connection_state == "MARKET CLOSED"
    assert adapter.is_connected is False


def test_websocket_streaming_and_subscriptions():
    """Test full WebSocket synchronization: snapshot, subscribe, forming candle, completion."""
    from starlette.testclient import TestClient

    # Use Starlette TestClient which supports websocket_connect
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # 1. First message must be INITIAL_SNAPSHOT
            init_msg = ws.receive_json()
            assert init_msg["type"] == "INITIAL_SNAPSHOT"
            assert "data" in init_msg
            assert "nifty_price" in init_msg["data"]
            assert "connection_state" in init_msg["data"]

            # 2. Client sends ping
            ws.send_text("ping")
            resp = ws.receive_text()
            assert resp == "pong"

            # 3. Client sends JSON PING
            ws.send_json({"type": "PING"})
            pong_resp = ws.receive_json()
            assert pong_resp["type"] == "PONG"

            # 4. Client sends SUBSCRIBE
            ws.send_json({"type": "SUBSCRIBE", "symbols": ["NIFTY 50", "NIFTY 25500 CE"]})
            sub_ack = ws.receive_json()
            assert sub_ack["type"] == "SUBSCRIBED"
            assert "NIFTY 25500 CE" in sub_ack["symbols"]
            assert "NIFTY 50" in coordinator.active_subscriptions
            assert "NIFTY 25500 CE" in coordinator.active_subscriptions

            # 5. Simulate NIFTY spot tick
            spot_tick = MarketTickData(
                instrument_token="26000",
                exchange_segment="nse_cm",
                symbol="NIFTY 50",
                last_price=25520.50,
                timestamp=datetime.now(timezone.utc),
                volume=500,
                bid=25520.25,
                ask=25520.75,
                is_index=True
            )
            coordinator.on_tick(spot_tick)

            # Receive broadcasted messages
            received_types = set()
            for _ in range(5):
                try:
                    msg = ws.receive_json()
                    received_types.add(msg["type"])
                    if "TICK" in received_types and "FORMING_CANDLE" in received_types and "OPTION_CHAIN_SPOT" in received_types:
                        break
                except Exception:
                    break

            assert "TICK" in received_types
            assert "FORMING_CANDLE" in received_types
            assert "OPTION_CHAIN_SPOT" in received_types

            # 6. Simulate Option tick
            opt_tick = MarketTickData(
                instrument_token="64473",
                exchange_segment="nse_fo",
                symbol="NIFTY 25500 CE",
                last_price=165.40,
                timestamp=datetime.now(timezone.utc),
                volume=1200,
                open_interest=75000,
                bid=165.30,
                ask=165.50,
                is_index=False
            )
            coordinator.on_tick(opt_tick)

            opt_types = set()
            for _ in range(5):
                try:
                    msg = ws.receive_json()
                    opt_types.add(msg["type"])
                    if "TICK" in opt_types and "OPTION_CHAIN_TICK" in opt_types:
                        break
                except Exception:
                    break

            assert "TICK" in opt_types
            assert "OPTION_CHAIN_TICK" in opt_types

            # 7. Simulate Candle Completed
            completed_bar = CandleData(
                timestamp=datetime.now(timezone.utc),
                open=25500.0,
                high=25525.0,
                low=25495.0,
                close=25520.0,
                volume=15000.0,
                complete=True
            )
            coordinator.on_candle_completed("NIFTY 50", completed_bar)

            # Look for CANDLE_COMPLETED message in incoming queue
            candle_msg = None
            for idx in range(100):
                m = ws.receive_json()
                if m.get("type") == "CANDLE_COMPLETED":
                    candle_msg = m
                    break

            assert candle_msg is not None
            assert candle_msg["type"] == "CANDLE_COMPLETED"
            assert candle_msg["data"]["symbol"] == "NIFTY 50"
            assert candle_msg["data"]["close"] == 25520.0
            assert candle_msg["data"]["complete"] is True

            assert candle_msg is not None
            assert candle_msg["type"] == "CANDLE_COMPLETED"
            assert candle_msg["data"]["symbol"] == "NIFTY 50"
            assert candle_msg["data"]["close"] == 25520.0
            assert candle_msg["data"]["complete"] is True
