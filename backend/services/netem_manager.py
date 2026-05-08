"""
Applies and removes tc netem network conditions on the selected client VM
(VM2 by default; optionally VM3).
All parameters come from config.yaml — no hardcoded values.
"""

from __future__ import annotations

import asyncio

from backend.core.config import NetworkConditionPreset, get_config
from backend.core.logging import get_logger
from backend.services.ssh_manager import SshManager

logger = get_logger(__name__)


class NetemManager:
    def __init__(self, ssh: SshManager, *, client_vm: str = "vm2") -> None:
        self._ssh = ssh
        self._cfg = get_config()
        self._detected_iface: str | None = None
        self._client_vm = client_vm

    async def _run_client(self, command: str, *, check: bool = True):
        if self._client_vm == "vm3":
            return await self._ssh.run_vm3(command, check=check)
        return await self._ssh.run_vm2(command, check=check)

    async def _get_iface(self) -> str:
        """Return client VM network interface, auto-detecting via `ip route`."""
        if self._detected_iface:
            return self._detected_iface
        if self._client_vm == "vm3" and self._cfg.infrastructure.vm3 is not None:
            configured = self._cfg.infrastructure.vm3.network_interface
        else:
            configured = self._cfg.infrastructure.vm2.network_interface
        try:
            result = await self._run_client(
                "ip route show default | awk '/default/ {print $5; exit}'",
                check=False,
            )
            detected = (result.stdout or "").strip()
            if detected:
                if detected != configured:
                    logger.info("iface_autodetected", configured=configured, detected=detected)
                self._detected_iface = detected
                return detected
        except Exception:
            pass
        self._detected_iface = configured
        return configured

    def _build_netem_cmd(self, iface: str, preset: NetworkConditionPreset) -> str:
        """
        Constructs the full `tc qdisc` command for the given preset.
        Adds netem sub-commands only when the relevant values are non-zero.
        """
        parts: list[str] = [
            f"sudo tc qdisc replace dev {iface} root netem"
        ]

        if preset.delay_ms > 0:
            delay_part = f"delay {preset.delay_ms}ms"
            if preset.jitter_ms > 0:
                delay_part += f" {preset.jitter_ms}ms distribution normal"
            parts.append(delay_part)

        if preset.loss_percent > 0:
            parts.append(f"loss {preset.loss_percent}%")

        if preset.rate_mbit > 0:
            parts.append(f"rate {preset.rate_mbit}mbit")

        return " ".join(parts)

    async def apply(self, condition_key: str) -> None:
        if condition_key == "real_time":
            logger.info("netem_bypass", condition=condition_key, reason="no_emulation")
            await self.reset()
            return

        preset = self._cfg.network_conditions[condition_key]
        iface = await self._get_iface()
        cmd = self._build_netem_cmd(iface, preset)

        logger.info("netem_apply", condition=condition_key, cmd=cmd)
        await self._run_client(cmd)

        if preset.hping3_flood and preset.hping3_target and preset.hping3_duration_sec:
            await self._start_hping3(preset)

    async def _start_hping3(self, preset: NetworkConditionPreset) -> None:
        duration = preset.hping3_duration_sec
        target = preset.hping3_target
        cmd = (
            f"sudo hping3 --syn --flood -V -p 80 "
            f"{target} &> /tmp/hping3.log & disown"
        )
        logger.info("hping3_start", target=target, duration=duration)
        await self._run_client(cmd)

        # Schedule automatic stop after duration
        asyncio.get_event_loop().call_later(
            duration, lambda: asyncio.ensure_future(self._stop_hping3())
        )

    async def _stop_hping3(self) -> None:
        logger.info("hping3_stop")
        await self._run_client("sudo killall hping3 2>/dev/null || true", check=False)

    async def reset(self) -> None:
        iface = await self._get_iface()
        cmd = f"sudo tc qdisc del dev {iface} root 2>/dev/null || true"
        logger.info("netem_reset", iface=iface)
        await self._run_client(cmd, check=False)
        await self._stop_hping3()
