"""Offline smoke tests for the Cloud Run health endpoints."""

import asyncio
import importlib.util
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_health_routes():
    """Import the app without credentials or telemetry and check both routes."""
    settings = SimpleNamespace(logfire_token=None, logfire_env="test")
    loop = asyncio.new_event_loop()
    spec = importlib.util.find_spec("policyengine_github_bot.main")
    assert spec is not None and spec.loader is not None
    main = importlib.util.module_from_spec(spec)

    try:
        with (
            patch("policyengine_github_bot.config.get_settings", return_value=settings),
            patch("asyncio.get_event_loop", return_value=loop),
            patch("logfire.configure"),
            patch("logfire.instrument_fastapi"),
            patch("logfire.instrument_requests"),
        ):
            # Execute in an isolated module so other tests' imports cannot affect setup.
            spec.loader.exec_module(main)

        with TestClient(main.app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}

            response = client.get("/")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "policyengine-github-bot"}
    finally:
        if hasattr(main, "executor"):
            main.executor.shutdown(wait=True)
        loop.close()
