"""
Collects latency, throughput, and CPU metrics from the VMs.
Streams results via an async callback so the WebSocket handler
can forward them to the browser in real-time.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable

from backend.core.config import get_config
from backend.core.logging import get_logger
from backend.models.schemas import (
    CpuSample,
    LatencySample,
    ProtocolTestResult,
    ThroughputSample,
    WsCpuMessage,
    WsLatencyMessage,
    WsThroughputMessage,
)
from backend.services.ssh_manager import SshManager

logger = get_logger(__name__)

# Type alias for the streaming callback
StreamCallback = Callable[[dict], Awaitable[None]]

_PING_RE = re.compile(r"time=(?P<ms>[\d.]+)\s*ms")
_PING_LOSS_RE = re.compile(r"(?P<loss>[\d.]+)% packet loss")


class MetricsCollector:
    def __init__(self, ssh: SshManager, *, client_vm: str = "vm2") -> None:
        self._ssh = ssh
        self._cfg = get_config()
        self._client_vm = client_vm

    def _pool_client(self):
        if self._client_vm == "vm3":
            return self._ssh.pool_vm3()
        return self._ssh.pool_vm2()

    async def _run_client(self, command: str, *, check: bool = True):
        if self._client_vm == "vm3":
            return await self._ssh.run_vm3(command, check=check)
        return await self._ssh.run_vm2(command, check=check)

    # ── Latency ───────────────────────────────────────────────────────────────

    async def collect_latency(
        self,
        protocol: str,
        target_ip: str,
        callback: StreamCallback,
    ) -> list[LatencySample]:
        cfg = self._cfg.tests.latency
        interval = cfg.ping_interval_sec
        count = cfg.ping_count

        cmd = f"ping -i {interval} -c {count} {target_ip}"
        samples: list[LatencySample] = []

        logger.info("latency_start", protocol=protocol, target=target_ip, count=count)

        pool = self._pool_client()
        async for line in pool.stream_run(cmd):
            m = _PING_RE.search(line)
            if m:
                ts = time.time()
                value = float(m.group("ms"))
                sample = LatencySample(timestamp=ts, value_ms=value)
                samples.append(sample)
                msg = WsLatencyMessage(
                    protocol=protocol, timestamp=ts, value_ms=value
                )
                await callback(msg.model_dump())

        logger.info("latency_done", protocol=protocol, samples=len(samples))
        return samples

    # ── Throughput ────────────────────────────────────────────────────────────

    async def collect_throughput(
        self,
        protocol: str,
        server_ip: str,
        callback: StreamCallback,
    ) -> list[ThroughputSample]:
        cfg = self._cfg.tests.throughput
        iperf_port = self._cfg.infrastructure.vm1.iperf3_port
        duration = cfg.iperf3_duration_sec
        parallel = cfg.iperf3_parallel

        if protocol == "ipsec":
            await self._ensure_ipsec_route(server_ip)

        samples: list[ThroughputSample] = []

        # Upload (client → server)
        upload_mbps = await self._run_iperf3(
            direction="upload",
            server_ip=server_ip,
            port=iperf_port,
            duration=duration,
            parallel=parallel,
        )

        # Download (server → client, reversed)
        download_mbps = await self._run_iperf3(
            direction="download",
            server_ip=server_ip,
            port=iperf_port,
            duration=duration,
            parallel=parallel,
            reverse=True,
        )

        ts = time.time()
        sample = ThroughputSample(
            timestamp=ts, upload_mbps=upload_mbps, download_mbps=download_mbps
        )
        samples.append(sample)

        msg = WsThroughputMessage(
            protocol=protocol,
            timestamp=ts,
            upload_mbps=upload_mbps,
            download_mbps=download_mbps,
        )
        await callback(msg.model_dump())

        # Best-effort cleanup in case an interrupted test left a daemon behind.
        await self._ssh.run_vm1("pkill iperf3 2>/dev/null || true", check=False)

        logger.info(
            "throughput_done",
            protocol=protocol,
            upload=upload_mbps,
            download=download_mbps,
        )
        return samples

    async def _run_iperf3(
        self,
        *,
        direction: str,
        server_ip: str,
        port: int,
        duration: int,
        parallel: int,
        reverse: bool = False,
    ) -> float:
        last_error: Exception | None = None
        for attempt in range(1, 3):
            try:
                await self._start_iperf3_server(port)
                return await self._run_iperf3_once(
                    direction=direction,
                    server_ip=server_ip,
                    port=port,
                    duration=duration,
                    parallel=parallel,
                    reverse=reverse,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "iperf3_attempt_failed",
                    direction=direction,
                    attempt=attempt,
                    exc=str(exc),
                )
                if attempt == 1:
                    await asyncio.sleep(1)
        assert last_error is not None
        raise last_error

    async def _run_iperf3_once(
        self,
        *,
        direction: str,
        server_ip: str,
        port: int,
        duration: int,
        parallel: int,
        reverse: bool = False,
    ) -> float:
        rev_flag = "-R" if reverse else ""
        # VM3 commonly runs under WSL2/Tailscale, where the final iperf3 JSON
        # control message can arrive late when the path is lossy or MTU-sensitive.
        timeout_sec = duration + (35 if self._client_vm == "vm3" else 20)
        # iperf3 expects --connect-timeout in milliseconds, not seconds.
        connect_timeout_ms = 10000 if self._client_vm == "vm3" else 5000
        cmd = (
            f"timeout {timeout_sec} "
            f"iperf3 -c {server_ip} -p {port} -t {duration} "
            f"--connect-timeout {connect_timeout_ms} "
            f"-P {parallel} -J {rev_flag}"
        )
        result = await self._run_client(cmd, check=False)
        
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            from backend.services.ssh_manager import SshCommandError
            stderr = result.stderr or ""
            stdout = result.stdout or ""
            details = stderr or stdout or "Invalid JSON and no stderr/stdout"
            raise SshCommandError(cmd, result.exit_status, details)
            
        if "error" in data:
            from backend.services.ssh_manager import SshCommandError
            raise SshCommandError(cmd, result.exit_status, data["error"])
        if result.exit_status != 0:
            from backend.services.ssh_manager import SshCommandError
            raise SshCommandError(
                cmd,
                result.exit_status,
                result.stderr or result.stdout or "iperf3 failed without output",
            )

        try:
            bits_per_sec = data["end"]["sum_received"]["bits_per_second"]
        except KeyError:
            try:
                bits_per_sec = data["end"]["sum_sent"]["bits_per_second"]
            except KeyError:
                bits_per_sec = 0.0

        mbps = bits_per_sec / 1_000_000
        logger.debug("iperf3_result", direction=direction, mbps=mbps)
        return round(mbps, 2)

    async def _start_iperf3_server(self, port: int) -> None:
        await self._ssh.run_vm1(
            "sudo iptables -I INPUT -s 10.8.0.0/24 -p tcp --dport "
            f"{port} -j ACCEPT 2>/dev/null || true; "
            "sudo iptables -I INPUT -s 10.9.0.0/24 -p tcp --dport "
            f"{port} -j ACCEPT 2>/dev/null || true; "
            "sudo iptables -I INPUT -s 10.10.0.0/24 -p tcp --dport "
            f"{port} -j ACCEPT 2>/dev/null || true; "
            "sudo iptables -I INPUT -s 10.200.0.0/24 -p tcp --dport "
            f"{port} -j ACCEPT 2>/dev/null || true; "
            "sudo pkill iperf3 2>/dev/null || true; "
            "sleep 0.5; "
            f"sudo rm -f /tmp/iperf3.log; "
            f"sudo iperf3 -s -p {port} -D --logfile /tmp/iperf3.log; "
            "sleep 1; "
            f"sudo ss -ltn sport = :{port} | grep -q ':{port}' || "
            f"(sudo cat /tmp/iperf3.log >&2 2>/dev/null; exit 1)"
        )

    async def _ensure_ipsec_route(self, server_ip: str) -> None:
        client_ip = self._cfg.vpn.ipsec.client_vpn_ip
        if self._client_vm == "vm3" and self._cfg.infrastructure.vm3 is not None:
            iface = self._cfg.infrastructure.vm3.network_interface or "tailscale0"
        else:
            iface = self._cfg.infrastructure.vm2.network_interface or "tailscale0"
        await self._run_client(
            f"sudo ip route replace {server_ip}/32 dev {iface} src {client_ip}",
            check=False,
        )

    # ── CPU ───────────────────────────────────────────────────────────────────

    async def collect_cpu(
        self,
        callback: StreamCallback,
    ) -> list[CpuSample]:
        cfg = self._cfg.tests.cpu
        interval = cfg.vmstat_interval_sec
        samples_n = cfg.vmstat_samples

        cmd = f"vmstat {interval} {samples_n}"
        result = await self._ssh.run_vm1(cmd)

        lines = result.stdout.strip().splitlines()
        # vmstat output: header line, units line, then data lines
        data_lines = lines[2:]
        cpu_samples: list[CpuSample] = []

        for line in data_lines:
            parts = line.split()
            if len(parts) < 15:
                continue
            # Column 14 is idle CPU %; usage = 100 - idle
            try:
                idle = float(parts[14])
                usage = round(100.0 - idle, 1)
            except (ValueError, IndexError):
                continue

            ts = time.time()
            sample = CpuSample(host="vm1", timestamp=ts, usage_percent=usage)
            cpu_samples.append(sample)

            msg = WsCpuMessage(host="vm1", timestamp=ts, usage_percent=usage)
            await callback(msg.model_dump())

        logger.info("cpu_done", samples=len(cpu_samples))
        return cpu_samples
