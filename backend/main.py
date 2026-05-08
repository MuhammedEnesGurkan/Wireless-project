"""
VPN Benchmark Suite — FastAPI application entry point.
Configures middleware, mounts routers, and handles graceful shutdown.
"""

from __future__ import annotations

import signal
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_config
from backend.core.logging import configure_logging, get_logger
from backend.routers.config import router as config_router
from backend.routers.tests import router as tests_router
from backend.services.ssh_manager import get_ssh_manager

from dotenv import load_dotenv
load_dotenv(dotenv_path=__file__[: __file__.rfind("backend")] + ".env", override=False)

configure_logging()
logger = get_logger(__name__)


def _init_runtime_config_from_env() -> None:
    """
    Pre-populate the in-memory runtime config from environment variables
    so the Settings panel is already filled in on first open.
    Priority: .env > config.yaml defaults.
    """
    import os
    from backend.services.runtime_config import update_runtime_config

    cfg = get_config()

    vm1_password = os.getenv("VM1_SSH_PASSWORD", "")
    vm2_password = os.getenv("VM2_SSH_PASSWORD", "")
    vm3_password = os.getenv("VM3_SSH_PASSWORD", "")

    cfg_vm3 = cfg.infrastructure.vm3

    update_runtime_config(
        vm1_host=os.getenv("VM1_HOST", cfg.infrastructure.vm1.host),
        vm1_port=int(os.getenv("VM1_SSH_PORT", str(cfg.infrastructure.vm1.port))),
        vm1_user=os.getenv("VM1_SSH_USER", cfg.infrastructure.vm1.user),
        vm1_ssh_key_path=os.getenv("VM1_SSH_KEY_PATH", cfg.infrastructure.vm1.ssh_key_path),
        vm1_ssh_password=vm1_password,
        vm1_use_password_auth=bool(vm1_password),

        vm2_host=os.getenv("VM2_HOST", cfg.infrastructure.vm2.host),
        vm2_port=int(os.getenv("VM2_SSH_PORT", str(cfg.infrastructure.vm2.port))),
        vm2_user=os.getenv("VM2_SSH_USER", cfg.infrastructure.vm2.user),
        vm2_ssh_key_path=os.getenv("VM2_SSH_KEY_PATH", cfg.infrastructure.vm2.ssh_key_path),
        vm2_ssh_password=vm2_password,
        vm2_use_password_auth=bool(vm2_password),

        vm3_host=os.getenv("VM3_HOST", cfg_vm3.host if cfg_vm3 else ""),
        vm3_port=int(os.getenv("VM3_SSH_PORT", str(cfg_vm3.port if cfg_vm3 else 22))),
        vm3_user=os.getenv("VM3_SSH_USER", cfg_vm3.user if cfg_vm3 else ""),
        vm3_ssh_key_path=os.getenv("VM3_SSH_KEY_PATH", cfg_vm3.ssh_key_path if cfg_vm3 else ""),
        vm3_ssh_password=vm3_password,
        vm3_use_password_auth=bool(vm3_password),
    )
    logger.info(
        "runtime_config_initialized",
        vm1=os.getenv("VM1_HOST", cfg.infrastructure.vm1.host),
        vm2=os.getenv("VM2_HOST", cfg.infrastructure.vm2.host),
        vm3=os.getenv("VM3_HOST", cfg_vm3.host if cfg_vm3 else ""),
        auth="password" if vm1_password else "key",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = get_config()
    _init_runtime_config_from_env()
    logger.info(
        "app_startup",
        host=cfg.backend.host,
        port=cfg.backend.port,
        ws_path=cfg.backend.websocket_path,
    )
    yield
    logger.info("app_shutdown")
    ssh = get_ssh_manager()
    await ssh.shutdown()


def create_app() -> FastAPI:
    cfg = get_config()

    app = FastAPI(
        title="VPN Benchmark Suite",
        description=(
            "Network Condition-Aware VPN Benchmark Suite. "
            "Streams live latency, throughput and CPU metrics via WebSocket."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.backend.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(tests_router)
    app.include_router(config_router)
    return app


app = create_app()


def _install_signal_handlers() -> None:
    """Install SIGTERM handler so Docker stop / systemctl stop triggers cleanup."""
    try:
        loop = asyncio.get_running_loop()

        def _handle_sigterm() -> None:
            logger.info("sigterm_received")
            loop.stop()

        loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)
    except (NotImplementedError, RuntimeError):
        # Windows does not support add_signal_handler
        pass


if __name__ == "__main__":
    cfg = get_config()
    uvicorn.run(
        "backend.main:app",
        host=cfg.backend.host,
        port=cfg.backend.port,
        reload=False,
        log_config=None,
        access_log=False,
    )
