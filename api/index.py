import sys
import os
from pathlib import Path

# Add project root to sys.path so 'backend' package is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import app

# Vercel Serverless Function entrypoint
# The 'app' object is the ASGI FastAPI instance
