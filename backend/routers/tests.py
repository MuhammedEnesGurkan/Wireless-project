"""
HTTP + WebSocket router for test lifecycle.
POST /api/test/start  — validates input, kicks off background test task
POST /api/test/stop   — cancels running test
GET  /api/test/status — current state
GET  /api/health      — liveness probe
WS   /ws/test         — streams all events to the browser
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from backend.core.config import get_config
from backend.core.logging import get_logger
from backend.models.schemas import (
    HealthResponse,
    NetworkCondition,
    ProtocolTestResult,
    StartTestRequest,
    StopTestRequest,
    TestPhase,
    TestStatusResponse,
    VpnProtocol,
    WsErrorMessage,
    WsHeartbeat,
    WsProgressMessage,
    WsResultFinal,
    WsStatusMessage,
)
from backend.services.metrics_collector import MetricsCollector
from backend.services.netem_manager import NetemManager
from backend.services.ssh_manager import SshCommandError, get_ssh_manager
from backend.services.vpn_manager import TunnelVerificationError, VpnManager

logger = get_logger(__name__)
router = APIRouter()


# ── In-memory test state ──────────────────────────────────────────────────────

class TestState:
    def __init__(self) -> None:
        self.running: bool = False
        self.phase: TestPhase = TestPhase.IDLE
        self.protocol: VpnProtocol | None = None
        self.condition: NetworkCondition | None = None
        self.task: asyncio.Task | None = None
        self.results: list[ProtocolTestResult] = []
        self.clients: set[WebSocket] = set()

    def reset(self) -> None:
        self.running = False
        self.phase = TestPhase.IDLE
        self.protocol = None
        self.condition = None
        self.task = None
        self.results = []


_state = TestState()


# ── WebSocket broadcast helpers ───────────────────────────────────────────────

async def broadcast(message: dict[str, Any]) -> None:
    dead: set[WebSocket] = set()
    payload = json.dumps(message)
    for ws in _state.clients:
        try:
            await ws.send_text(payload)
        except Exception:  # noqa: BLE001
            dead.add(ws)
    _state.clients -= dead


async def send_status(phase: str, message: str) -> None:
    await broadcast(WsStatusMessage(phase=phase, message=message).model_dump())


async def send_progress(percent: int, label: str) -> None:
    await broadcast(WsProgressMessage(percent=percent, label=label).model_dump())


async def send_error(phase: str, message: str, retry: bool = False) -> None:
    await broadcast(
        WsErrorMessage(phase=phase, message=message, retry=retry).model_dump()
    )


# ── Scoring ───────────────────────────────────────────────────────────────────

def compute_score(result: ProtocolTestResult) -> float:
    cfg = get_config().scoring
    app_cfg = get_config()

    if result.avg_latency_ms <= 0 or result.avg_throughput_mbps < 0:
        return 0.0

    condition = app_cfg.network_conditions.get(result.condition)
    if condition is None:
        logger.warning("score_condition_missing", condition=result.condition)
        return 0.0

    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    # Condition-aware targets
    latency_target_ms = max(20.0, float(condition.delay_ms + condition.jitter_ms + 20))
    throughput_target_mbps = float(condition.rate_mbit) if condition.rate_mbit > 0 else 100.0
    expected_loss_pct = float(condition.loss_percent)
    loss_tolerance_pct = max(1.0, expected_loss_pct + 1.5)

    # Measured packet loss from ping sample completeness
    expected_pings = max(app_cfg.tests.latency.ping_count, 1)
    received_pings = len(result.latency_samples)
    measured_loss_pct = max(0.0, (expected_pings - received_pings) / expected_pings * 100.0)

    latency_values = [sample.value_ms for sample in result.latency_samples]
    latency_stddev = statistics.pstdev(latency_values) if len(latency_values) > 1 else 0.0
    # Estimate jitter as stddev of RTT; keep a reasonable floor for very stable links.
    jitter_target_ms = max(5.0, float(condition.jitter_ms) if condition.jitter_ms > 0 else 10.0)

    # Normalized sub-scores (0..1)
    latency_score = _clamp01(latency_target_ms / max(result.avg_latency_ms, 1e-6))
    throughput_score = _clamp01(result.avg_throughput_mbps / max(throughput_target_mbps, 1e-6))
    cpu_score = _clamp01(35.0 / max(result.avg_cpu_percent, 1.0))
    loss_score = _clamp01(1.0 - (measured_loss_pct / loss_tolerance_pct))
    stability_score = _clamp01(1.0 - (latency_stddev / max(jitter_target_ms, 1e-6)))

    # Keep existing config weights but reserve budget for loss + stability.
    base_scale = 0.75
    latency_weight = cfg.latency_weight * base_scale
    throughput_weight = cfg.throughput_weight * base_scale
    cpu_weight = cfg.cpu_weight * base_scale
    residual = max(0.0, 1.0 - (latency_weight + throughput_weight + cpu_weight))
    loss_weight = residual * 0.6
    stability_weight = residual * 0.4

    weighted = (
        latency_score * latency_weight
        + throughput_score * throughput_weight
        + cpu_score * cpu_weight
        + loss_score * loss_weight
        + stability_score * stability_weight
    )

    score = round(_clamp01(weighted) * cfg.score_max, 1)
    logger.info(
        "score_breakdown",
        protocol=result.protocol,
        condition=result.condition,
        score=score,
        latency_score=round(latency_score, 4),
        throughput_score=round(throughput_score, 4),
        cpu_score=round(cpu_score, 4),
        loss_score=round(loss_score, 4),
        stability_score=round(stability_score, 4),
        measured_loss_pct=round(measured_loss_pct, 3),
        latency_stddev=round(latency_stddev, 3),
        throughput_target_mbps=throughput_target_mbps,
        latency_target_ms=latency_target_ms,
    )

    return score


# ── Core test runner ──────────────────────────────────────────────────────────

PROTOCOL_ORDER = [
    VpnProtocol.WIREGUARD,
    VpnProtocol.OPENVPN_UDP,
    VpnProtocol.OPENVPN_TCP,
    VpnProtocol.IPSEC,
]

PROGRESS_STEPS = {
    "applying_condition":   10,
    "starting_vpn_server":  20,
    "connecting_client":    30,
    "verifying_tunnel":     40,
    "running_latency":      55,
    "running_throughput":   75,
    "collecting_cpu":       85,
    "calculating_score":    90,
    "cleaning_up":          95,
}


def _humanize_ssh_error(exc: SshCommandError) -> str:
    stderr = (exc.stderr or "").lower()
    cmd = (exc.cmd or "").lower()

    if "cannot find device" in stderr and "tc qdisc" in cmd:
        return (
            "SSH command failed: VM2 ağ arayüzü bulunamadı. "
            "Yeni sürüm arayüzü otomatik algılıyor; backend'i yeniden başlatıp testi tekrar deneyin."
        )

    if "unit wg-quick@wg0.service not found" in stderr:
        return (
            "SSH command failed: VM1'de WireGuard servisi bulunamadı "
            "(`wg-quick@wg0`). VM1 setup scriptini çalıştırın veya "
            "`/etc/wireguard/wg0.conf` + service kurulumunu tamamlayın."
        )

    if "not in the sudoers file" in stderr:
        return (
            "SSH command failed: SSH kullanıcısı sudo yetkisine sahip değil. "
            "VM içinde yetkili kullanıcıyla bu hesabı sudoers'a ekleyin."
        )

    return f"SSH command failed: {exc}"


async def _run_single_protocol(
    protocol: VpnProtocol,
    condition_key: str,
    ssh_mgr,
) -> ProtocolTestResult:
    cfg = get_config()
    vpn = VpnManager(ssh_mgr)
    netem = NetemManager(ssh_mgr)
    metrics = MetricsCollector(ssh_mgr)

    result = ProtocolTestResult(protocol=protocol.value, condition=condition_key)

    # ── Step 1: Apply network condition ───────────────────────────────────────
    _state.phase = TestPhase.APPLYING_CONDITION
    await send_status("applying_condition", f"Applying {condition_key} preset…")
    await send_progress(10, "Applying network condition")
    await netem.apply(condition_key)

    # ── Step 2: Start VPN server on VM1 ───────────────────────────────────────
    _state.phase = TestPhase.STARTING_VPN_SERVER
    await send_status("starting_vpn_server", f"Starting {protocol.value} server…")
    await send_progress(20, "Starting VPN server")
    await vpn.start_server(protocol)

    # ── Step 3: Connect VPN client on VM2 ─────────────────────────────────────
    _state.phase = TestPhase.CONNECTING_CLIENT
    await send_status("connecting_client", "Connecting VPN client…")
    await send_progress(30, "Connecting VPN client")
    await vpn.start_client(protocol)

    # ── Step 4: Verify tunnel ─────────────────────────────────────────────────
    _state.phase = TestPhase.VERIFYING_TUNNEL
    await send_status("verifying_tunnel", "Verifying tunnel connectivity…")
    await send_progress(40, "Verifying tunnel")
    try:
        await vpn.verify_tunnel(protocol)
        await send_status("verifying_tunnel", "✅ Tunnel verified")
    except TunnelVerificationError as exc:
        await send_error("tunnel_verify", str(exc), retry=False)
        raise

    # ── Step 5: Latency test ──────────────────────────────────────────────────
    _state.phase = TestPhase.RUNNING_LATENCY
    vpn_ip = vpn._get_server_vpn_ip(protocol)
    await send_status("running_latency", "Running latency test (ping)…")
    await send_progress(55, "Collecting latency samples")

    result.latency_samples = await metrics.collect_latency(
        protocol=protocol.value,
        target_ip=vpn_ip,
        callback=broadcast,
    )

    # ── Step 6: Throughput test ───────────────────────────────────────────────
    _state.phase = TestPhase.RUNNING_THROUGHPUT
    await send_status("running_throughput", "Running throughput test (iperf3)…")
    await send_progress(75, "Measuring throughput")

    result.throughput_samples = await metrics.collect_throughput(
        protocol=protocol.value,
        server_ip=vpn_ip,
        callback=broadcast,
    )

    # ── Step 7: CPU collection ────────────────────────────────────────────────
    _state.phase = TestPhase.COLLECTING_CPU
    await send_status("collecting_cpu", "Collecting CPU usage (vmstat)…")
    await send_progress(85, "Collecting CPU metrics")

    result.cpu_samples = await metrics.collect_cpu(callback=broadcast)

    # ── Step 8: Score ─────────────────────────────────────────────────────────
    _state.phase = TestPhase.CALCULATING_SCORE
    await send_progress(90, "Calculating score")

    # Re-validate aggregates (model_validator only fires on construction)
    result = ProtocolTestResult.model_validate(result.model_dump())
    result.score = compute_score(result)

    # ── Step 9: Cleanup ───────────────────────────────────────────────────────
    _state.phase = TestPhase.CLEANING_UP
    await send_status("cleaning_up", "Cleaning up tunnel and conditions…")
    await send_progress(95, "Cleaning up")

    await vpn.stop_client(protocol)
    await vpn.stop_server(protocol)
    await netem.reset()

    await send_progress(100, "Done")
    return result


async def _run_test(condition: NetworkCondition, protocol: VpnProtocol) -> None:
    ssh_mgr = get_ssh_manager()
    condition_key = condition.value if hasattr(condition, "value") else condition
    protocols = (
        PROTOCOL_ORDER if protocol == VpnProtocol.ALL else [protocol]
    )

    _state.results.clear()

    try:
        for proto in protocols:
            if not _state.running:
                break
            logger.info("test_start", protocol=proto, condition=condition_key)
            await send_status(
                "starting",
                f"▶ Starting {proto.value} under {condition_key}",
            )

            result = await _run_single_protocol(proto, condition_key, ssh_mgr)
            _state.results.append(result)

        # Mark best result as recommended
        if _state.results:
            best = max(_state.results, key=lambda r: r.score)
            best.recommended = True

        # Send final results
        for res in _state.results:
            final = WsResultFinal(
                protocol=res.protocol,
                condition=res.condition,
                avg_latency_ms=res.avg_latency_ms,
                max_latency_ms=res.max_latency_ms,
                avg_throughput_mbps=res.avg_throughput_mbps,
                avg_cpu_percent=res.avg_cpu_percent,
                score=res.score,
                recommended=res.recommended,
            )
            await broadcast(final.model_dump())

        _state.phase = TestPhase.COMPLETE
        await send_status("complete", "✅ All tests complete")

    except asyncio.CancelledError:
        logger.info("test_cancelled")
        await send_error("cancelled", "Test was stopped by user")
        await _emergency_cleanup(protocols, condition_key, ssh_mgr)
    except SshCommandError as exc:
        logger.error("ssh_error", exc=str(exc))
        await send_error("ssh_error", _humanize_ssh_error(exc))
        await _emergency_cleanup(protocols, condition_key, ssh_mgr)
    except TunnelVerificationError as exc:
        logger.error("tunnel_error", exc=str(exc))
        await _emergency_cleanup(protocols, condition_key, ssh_mgr)
    except Exception as exc:  # noqa: BLE001
        logger.exception("test_error", exc=str(exc))
        await send_error("unknown", f"Unexpected error: {exc}")
        await _emergency_cleanup(protocols, condition_key, ssh_mgr)
    finally:
        _state.running = False
        _state.phase = TestPhase.IDLE


async def _emergency_cleanup(
    protocols: list[VpnProtocol],
    condition_key: str,
    ssh_mgr,
) -> None:
    """Best-effort cleanup after errors or cancellation."""
    vpn = VpnManager(ssh_mgr)
    netem = NetemManager(ssh_mgr)
    try:
        for proto in protocols:
            await vpn.stop_client(proto)
            await vpn.stop_server(proto)
        await netem.reset()
    except Exception as exc:  # noqa: BLE001
        logger.warning("cleanup_error", exc=str(exc))


# ── HTTP Endpoints ────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="1.0.0")


@router.post("/api/test/start")
async def start_test(req: StartTestRequest) -> JSONResponse:
    if _state.running:
        return JSONResponse(
            status_code=409,
            content={"detail": "A test is already running"},
        )

    _state.running = True
    _state.protocol = VpnProtocol(req.protocol)
    _state.condition = NetworkCondition(req.condition)
    _state.phase = TestPhase.APPLYING_CONDITION

    _state.task = asyncio.create_task(
        _run_test(_state.condition, _state.protocol)
    )

    logger.info("test_requested", protocol=req.protocol, condition=req.condition)
    return JSONResponse(
        status_code=202,
        content={"message": "Test started", "protocol": req.protocol, "condition": req.condition},
    )


@router.post("/api/test/stop")
async def stop_test(req: StopTestRequest) -> JSONResponse:
    if not _state.running or _state.task is None:
        return JSONResponse(
            status_code=400,
            content={"detail": "No test is running"},
        )

    _state.task.cancel()
    _state.running = False

    logger.info("test_stop_requested", reason=req.reason)
    return JSONResponse(content={"message": "Stop signal sent"})


@router.get("/api/test/status", response_model=TestStatusResponse)
async def test_status() -> TestStatusResponse:
    return TestStatusResponse(
        running=_state.running,
        phase=_state.phase,
        protocol=_state.protocol,
        condition=_state.condition,
    )


@router.get("/api/presets")
async def list_presets() -> JSONResponse:
    cfg = get_config()
    return JSONResponse(
        content={
            key: {
                "label": preset.label,
                "emoji": preset.emoji,
                "delay_ms": preset.delay_ms,
                "jitter_ms": preset.jitter_ms,
                "loss_percent": preset.loss_percent,
                "rate_mbit": preset.rate_mbit,
                "hping3_flood": preset.hping3_flood,
            }
            for key, preset in cfg.network_conditions.items()
        }
    )


# ── WebSocket Endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/test")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _state.clients.add(ws)
    cfg = get_config()
    heartbeat_interval = cfg.backend.websocket_heartbeat_sec

    logger.info("ws_connected", clients=len(_state.clients))

    async def heartbeat_loop() -> None:
        while True:
            await asyncio.sleep(heartbeat_interval)
            try:
                await ws.send_text(json.dumps(WsHeartbeat().model_dump()))
            except Exception:  # noqa: BLE001
                break

    hb_task = asyncio.create_task(heartbeat_loop())

    try:
        # Send current state immediately upon connection
        await ws.send_text(
            json.dumps(
                WsStatusMessage(
                    phase=_state.phase.value,
                    message="Connected to VPN Benchmark Suite",
                ).model_dump()
            )
        )

        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=heartbeat_interval * 2)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                continue  # Will be caught by heartbeat
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        hb_task.cancel()
        _state.clients.discard(ws)
        logger.info("ws_disconnected", clients=len(_state.clients))
