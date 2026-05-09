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
from backend.services.auto_repair import AutoRepairManager
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
    vm3: VmSettingsPayload | None = None


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
    vm3: VmSettingsResponse | None = None
    configured: bool


class ConnectivityResult(BaseModel):
    vm: str
    success: bool
    message: str
    latency_ms: Optional[float]


class AutoRepairRequest(BaseModel):
    apply_fixes: bool = Field(
        default=False,
        description="If true, run safe idempotent fixes over SSH after checks fail.",
    )


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
        vm3=_vm_resp(rt.vm3, cfg.infrastructure.vm3) if cfg.infrastructure.vm3 is not None else None,
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
        vm3_host=(payload.vm3.host if payload.vm3 else None),
        vm3_port=(payload.vm3.port if payload.vm3 else None),
        vm3_user=(payload.vm3.user if payload.vm3 else None),
        vm3_ssh_key_path=(payload.vm3.ssh_key_path or "" if payload.vm3 else None),
        vm3_ssh_password=(payload.vm3.ssh_password or "" if payload.vm3 else None),
        vm3_use_password_auth=(payload.vm3.use_password_auth if payload.vm3 else None),
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
    Try to SSH into all VMs in parallel and return connection results.
    All VMs are tested concurrently so total wait is max 12s, not 3x12s.
    """
    import time
    import socket as _socket

    cfg = get_config()
    ssh = get_ssh_manager()

    vm_names = ["vm1", "vm2"]
    if cfg.infrastructure.vm3 is not None:
        vm_names.append("vm3")

    # Reset SSH pools so we use the latest saved credentials
    await ssh.shutdown()

    async def _check_tcp(host: str, port: int, timeout: float = 3.0) -> str | None:
        """Return None if TCP port is open, else a human-readable error string."""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return None
        except asyncio.TimeoutError:
            return f"TCP port {port} zaman aşımı — VM kapalı veya port erişilemiyor"
        except ConnectionRefusedError:
            return f"TCP port {port} reddedildi — SSH servisi çalışmıyor (sudo systemctl start ssh)"
        except OSError as exc:
            raw = str(exc)
            if "getaddrinfo" in raw or "11001" in raw:
                return f"IP adresi çözümlenemedi ({host}) — IP doğru mu?"
            return f"Ağ hatası: {raw}"

    async def _test_vm(vm_name: str) -> ConnectivityResult:
        from backend.services.runtime_config import get_runtime_config
        from backend.core.config import get_config as _get_cfg

        _cfg = _get_cfg()
        rt = get_runtime_config()
        rt_vm = getattr(rt, vm_name)
        cfg_vm = getattr(_cfg.infrastructure, vm_name, None)

        host = rt_vm.host or (cfg_vm.host if cfg_vm else "")
        port = rt_vm.port or (cfg_vm.port if cfg_vm else 22)
        user = rt_vm.user or (cfg_vm.user if cfg_vm else "")

        # --- Step 1: quick TCP check ---
        tcp_err = await _check_tcp(host, port, timeout=4.0)
        if tcp_err:
            return ConnectivityResult(
                vm=vm_name, success=False,
                message=f"[{vm_name.upper()} {host}:{port}] {tcp_err}",
                latency_ms=None,
            )

        # --- Step 2: SSH auth check ---
        start = time.monotonic()
        try:
            run_fn = (
                ssh.run_vm1 if vm_name == "vm1"
                else ssh.run_vm2 if vm_name == "vm2"
                else ssh.run_vm3
            )
            result = await asyncio.wait_for(run_fn("echo ok"), timeout=10)
            elapsed = (time.monotonic() - start) * 1000

            if result.stdout.strip() == "ok":
                return ConnectivityResult(
                    vm=vm_name, success=True,
                    message=f"Bağlandı ✓  ({user}@{host}:{port})",
                    latency_ms=round(elapsed, 1),
                )
            return ConnectivityResult(
                vm=vm_name, success=False,
                message=f"Beklenmeyen çıktı: {result.stdout!r}",
                latency_ms=None,
            )

        except asyncio.TimeoutError:
            return ConnectivityResult(
                vm=vm_name, success=False,
                message=f"SSH kimlik doğrulaması zaman aşımına uğradı — şifre/anahtar doğru mu?",
                latency_ms=None,
            )
        except FileNotFoundError as exc:
            return ConnectivityResult(
                vm=vm_name, success=False,
                message=str(exc),
                latency_ms=None,
            )
        except Exception as exc:  # noqa: BLE001
            raw = str(exc)
            if "Authentication" in raw or "auth" in raw.lower() or "Permission denied" in raw:
                msg = f"SSH kimlik doğrulaması başarısız — kullanıcı adı ({user}), şifre veya SSH key yanlış olabilir"
            elif "No route" in raw or "10065" in raw:
                msg = "Host'a ulaşılamıyor — VM açık mı ve aynı ağda mı?"
            else:
                msg = raw
            return ConnectivityResult(
                vm=vm_name, success=False,
                message=msg,
                latency_ms=None,
            )

    # Run all VM checks concurrently
    tasks = [_test_vm(vm) for vm in vm_names]
    results = list(await asyncio.gather(*tasks))
    return results


@router.post("/auto-repair")
async def auto_repair(payload: AutoRepairRequest) -> JSONResponse:
    """
    Check all configured VMs/protocol prerequisites and optionally apply safe fixes.

    This does not regenerate WireGuard/OpenVPN keys silently. It fixes known
    idempotent pieces such as packages, IPsec/Tailscale plugins, CA copy,
    route helper, ipsec0, and benchmark firewall rules.
    """
    ssh = get_ssh_manager()
    repair = AutoRepairManager(ssh)
    report = await repair.run(apply_fixes=payload.apply_fixes)
    return JSONResponse(content=report.model_dump())
