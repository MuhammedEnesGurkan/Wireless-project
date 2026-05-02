"""
/api/config  — runtime infrastructure configuration endpoints.
Allows the frontend Settings panel to set VM IPs, SSH credentials, etc.
without restarting the backend.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.core.config import get_config
from backend.core.logging import get_logger
from backend.services.runtime_config import get_runtime_config, update_runtime_config
from backend.services.ssh_manager import get_ssh_manager

logger = get_logger(__name__)
router = APIRouter(prefix="/api/config", tags=["config"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class VmSettingsPayload(BaseModel):
    host: str = Field(..., min_length=1, description="IP address or hostname")
    port: int = Field(default=22, ge=1, le=65535)
    user: str = Field(..., min_length=1, description="SSH username")
    ssh_key_path: Optional[str] = Field(default=None, description="Path to SSH private key")
    ssh_password: Optional[str] = Field(default=None, description="SSH password (if not using key)")
    use_password_auth: bool = Field(default=False, description="Use password instead of key")


class InfrastructureSettingsPayload(BaseModel):
    vm1: VmSettingsPayload
    vm2: VmSettingsPayload


class VmSettingsResponse(BaseModel):
    host: str
    port: int
    user: str
    ssh_key_path: str
    use_password_auth: bool
    configured: bool


class InfrastructureSettingsResponse(BaseModel):
    vm1: VmSettingsResponse
    vm2: VmSettingsResponse
    configured: bool


class ConnectivityResult(BaseModel):
    vm: str
    success: bool
    message: str
    latency_ms: Optional[float]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=InfrastructureSettingsResponse)
async def get_infrastructure_config() -> InfrastructureSettingsResponse:
    """Return current (runtime-overridden) infrastructure config."""
    cfg = get_config()
    rt = get_runtime_config()

    def _vm_resp(rt_vm, cfg_vm) -> VmSettingsResponse:
        return VmSettingsResponse(
            host=rt_vm.host or cfg_vm.host,
            port=rt_vm.port if rt_vm.port != 22 else cfg_vm.port,
            user=rt_vm.user or cfg_vm.user,
            ssh_key_path=rt_vm.ssh_key_path or cfg_vm.ssh_key_path,
            use_password_auth=rt_vm.use_password_auth,
            configured=bool(rt_vm.host and rt_vm.user),
        )

    return InfrastructureSettingsResponse(
        vm1=_vm_resp(rt.vm1, cfg.infrastructure.vm1),
        vm2=_vm_resp(rt.vm2, cfg.infrastructure.vm2),
        configured=rt.configured,
    )


@router.post("", response_model=InfrastructureSettingsResponse)
async def save_infrastructure_config(
    payload: InfrastructureSettingsPayload,
) -> InfrastructureSettingsResponse:
    """Save VM connection settings. Clears SSH connection pool so new settings take effect."""
    update_runtime_config(
        vm1_host=payload.vm1.host,
        vm1_port=payload.vm1.port,
        vm1_user=payload.vm1.user,
        vm1_ssh_key_path=payload.vm1.ssh_key_path or "",
        vm1_ssh_password=payload.vm1.ssh_password or "",
        vm1_use_password_auth=payload.vm1.use_password_auth,
        vm2_host=payload.vm2.host,
        vm2_port=payload.vm2.port,
        vm2_user=payload.vm2.user,
        vm2_ssh_key_path=payload.vm2.ssh_key_path or "",
        vm2_ssh_password=payload.vm2.ssh_password or "",
        vm2_use_password_auth=payload.vm2.use_password_auth,
    )

    # Reset SSH pool so next connection uses new settings
    ssh = get_ssh_manager()
    await ssh.shutdown()

    logger.info(
        "runtime_config_updated",
        vm1_host=payload.vm1.host,
        vm2_host=payload.vm2.host,
    )

    return await get_infrastructure_config()


@router.post("/test-connectivity", response_model=list[ConnectivityResult])
async def test_connectivity() -> list[ConnectivityResult]:
    """
    Try to SSH into VM1 and VM2 and return connection results.
    Used by the Settings panel to verify credentials before running a test.
    """
    ssh = get_ssh_manager()
    results: list[ConnectivityResult] = []

    for vm_name in ("vm1", "vm2"):
        import time
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                ssh.run_vm1("echo ok") if vm_name == "vm1" else ssh.run_vm2("echo ok"),
                timeout=10,
            )
            elapsed = (time.monotonic() - start) * 1000
            if result.stdout.strip() == "ok":
                results.append(ConnectivityResult(
                    vm=vm_name, success=True,
                    message="Connected successfully",
                    latency_ms=round(elapsed, 1),
                ))
            else:
                results.append(ConnectivityResult(
                    vm=vm_name, success=False,
                    message=f"Unexpected output: {result.stdout!r}",
                    latency_ms=None,
                ))
        except asyncio.TimeoutError:
            results.append(ConnectivityResult(
                vm=vm_name, success=False,
                message="Bağlantı zaman aşımına uğradı (10 s) — VM açık mı ve SSH portu erişilebilir mi?",
                latency_ms=None,
            ))
        except FileNotFoundError as exc:
            results.append(ConnectivityResult(
                vm=vm_name, success=False,
                message=str(exc),
                latency_ms=None,
            ))
        except Exception as exc:  # noqa: BLE001
            raw = str(exc)
            # Map common socket errors to human-readable messages
            if "getaddrinfo failed" in raw or "11001" in raw:
                msg = f"IP adresi çözümlenemedi: '{raw}' — Girilen IP/hostname doğru mu?"
            elif "Connection refused" in raw or "10061" in raw:
                msg = "Bağlantı reddedildi — SSH servisi çalışıyor mu? (sudo systemctl start ssh)"
            elif "No route to host" in raw or "10065" in raw:
                msg = "Host'a ulaşılamıyor — VM açık mı ve aynı ağda mı?"
            elif "Authentication" in raw or "auth" in raw.lower():
                msg = "Kimlik doğrulama başarısız — SSH key veya şifre yanlış olabilir"
            elif "Permission denied" in raw:
                msg = "İzin reddedildi — SSH key doğru mu? Kullanıcı adı doğru mu?"
            else:
                msg = raw
            results.append(ConnectivityResult(
                vm=vm_name, success=False,
                message=msg,
                latency_ms=None,
            ))

    return results
