#!/usr/bin/env bash
# =============================================================================
# NEXTRADE — Backend Startup Script
# =============================================================================
set -e

PORT="${PORT:-8005}"
HOST="${HOST:-0.0.0.0}"

echo "=========================================================="
echo " Starting NEXTRADE Backend Server"
echo " Host: ${HOST} | Port: ${PORT}"
echo " Health Endpoint: http://${HOST}:${PORT}/api/health"
echo " Docs Endpoint:   http://${HOST}:${PORT}/docs"
echo "=========================================================="

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

exec uvicorn backend.app.main:app --host "${HOST}" --port "${PORT}" --reload
