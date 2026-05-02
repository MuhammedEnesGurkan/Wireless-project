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

_PING_RE = re.compile(
    r"icmp_seq=\d+ ttl=\d+ time=(?P<ms>[\d.]+) ms"
)
_PING_LOSS_RE = re.compile(r"(?P<loss>[\d.]+)% packet loss")


class MetricsCollector:
    def __init__(self, ssh: SshManager) -> None:
        self._ssh = ssh
        self._cfg = get_config()

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

        pool = self._ssh.pool_vm2()
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

        # Start iperf3 server on VM1 (non-blocking, daemonised)
        await self._ssh.run_vm1(
            f"pkill iperf3 2>/dev/null || true && "
            f"iperf3 -s -p {iperf_port} -D --logfile /tmp/iperf3.log"
        )
        await asyncio.sleep(1)

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

        # Stop iperf3 server
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
        rev_flag = "-R" if reverse else ""
        cmd = (
            f"iperf3 -c {server_ip} -p {port} -t {duration} "
            f"-P {parallel} -J {rev_flag}"
        )
        result = await self._ssh.run_vm2(cmd)
        data = json.loads(result.stdout)

        try:
            bits_per_sec = data["end"]["sum_received"]["bits_per_second"]
        except KeyError:
            bits_per_sec = data["end"]["sum_sent"]["bits_per_second"]

        mbps = bits_per_sec / 1_000_000
        logger.debug("iperf3_result", direction=direction, mbps=mbps)
        return round(mbps, 2)

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
