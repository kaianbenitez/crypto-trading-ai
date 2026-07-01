"""Windows helper — run the orchestrator as a foreground process.

For local testing:
    py orchestrator_service.py

For the VPS (Linux) use the systemd service file instead:
    deploy/trading-agent.service
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from agent.orchestrator import run

if __name__ == "__main__":
    run()
