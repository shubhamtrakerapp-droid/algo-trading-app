import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime, timezone
from typing import Dict, Any

from backend.app.coordinator import coordinator

logger = logging.getLogger("nextrade.ws")
router = APIRouter(tags=["WebSocket"])


def serialize_position(pos: Any) -> Any:
    """Ensure all datetime values inside position dict are converted to ISO strings."""
    if not pos or not isinstance(pos, dict):
        return None
    res = dict(pos)
    for k, v in res.items():
        if isinstance(v, datetime):
            res[k] = v.isoformat()
    return res


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket endpoint streaming market ticks, forming candles, 1-minute candle closes,
    strategy signals, live position updates, option chain updates, and paper trade execution events.
    """
    await websocket.accept()
    coordinator.active_websockets.add(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(coordinator.active_websockets)}")

    try:
        # Send initial state snapshot upon connection
        init_snapshot = coordinator.get_current_snapshot()
        init_payload = {
            "type": "INITIAL_SNAPSHOT",
            "data": init_snapshot
        }
        await websocket.send_text(json.dumps(init_payload, default=str))

        # Keep listening for client heartbeats, dynamic subscriptions, and requests
        while True:
            raw_data = await websocket.receive_text()
            if raw_data == "ping":
                await websocket.send_text("pong")
                continue

            try:
                msg = json.loads(raw_data)
                msg_type = str(msg.get("type", "")).upper()

                if msg_type == "PING":
                    await websocket.send_text(json.dumps({"type": "PONG", "timestamp": datetime.now(timezone.utc).isoformat()}))
                elif msg_type == "SUBSCRIBE":
                    symbols = msg.get("symbols", [])
                    if symbols and isinstance(symbols, list):
                        await coordinator.subscribe_symbols(symbols)
                        logger.debug(f"Client subscribed to symbols: {symbols}")
                        await websocket.send_text(json.dumps({
                            "type": "SUBSCRIBED",
                            "symbols": symbols,
                            "active_subscriptions": list(coordinator.active_subscriptions)
                        }))
                elif msg_type == "UNSUBSCRIBE":
                    symbols = msg.get("symbols", [])
                    if symbols and isinstance(symbols, list):
                        await coordinator.unsubscribe_symbols(symbols)
                        await websocket.send_text(json.dumps({
                            "type": "UNSUBSCRIBED",
                            "symbols": symbols,
                            "active_subscriptions": list(coordinator.active_subscriptions)
                        }))
                elif msg_type == "GET_SNAPSHOT":
                    snap = coordinator.get_current_snapshot()
                    await websocket.send_text(json.dumps({"type": "INITIAL_SNAPSHOT", "data": snap}, default=str))
            except json.JSONDecodeError:
                pass
            except Exception as msg_err:
                logger.debug(f"Error processing client message: {msg_err}")

    except WebSocketDisconnect:
        coordinator.active_websockets.discard(websocket)
        logger.info(f"WebSocket client disconnected. Remaining: {len(coordinator.active_websockets)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        coordinator.active_websockets.discard(websocket)
