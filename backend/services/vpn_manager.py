"""
VPN lifecycle manager — starts/stops server and client for each protocol.
All config comes from config.yaml.
"""

from __future__ import annotations

import asyncio

from backend.core.config import get_config
from backend.core.logging import get_logger
from backend.models.schemas import VpnProtocol
from backend.services.ssh_manager import SshManager

logger = get_logger(__name__)


class TunnelVerificationError(RuntimeError):
    pass


class VpnManager:
    def __init__(self, ssh: SshManager) -> None:
        self._ssh = ssh
        self._cfg = get_config()

    # ── Public API ─────────────────────────────────────────────────────────────

    async def start_server(self, protocol: VpnProtocol) -> None:
        service = self._get_server_service(protocol)
        logger.info("vpn_server_start", protocol=protocol, service=service)
        await self._ssh.run_vm1(f"sudo systemctl start {service}")
        await asyncio.sleep(2)  # Give service a moment to bind

    async def start_client(self, protocol: VpnProtocol) -> None:
        logger.info("vpn_client_start", protocol=protocol)
        cmd = self._get_client_connect_cmd(protocol)
        await self._ssh.run_vm2(cmd)
        await asyncio.sleep(3)

    async def verify_tunnel(self, protocol: VpnProtocol) -> None:
        """Ping VM1's VPN IP from VM2.  Retries up to verify_max_attempts."""
        vpn_ip = self._get_server_vpn_ip(protocol)
        cfg = self._cfg.tests.latency
        attempts = cfg.verify_max_attempts
        count = cfg.verify_ping_count

        for attempt in range(1, attempts + 1):
            logger.info(
                "tunnel_verify_attempt",
                attempt=attempt,
                vpn_ip=vpn_ip,
                protocol=protocol,
            )
            result = await self._ssh.run_vm2(
                f"ping -c {count} -W 3 {vpn_ip}",
                check=False,
            )
            if result.exit_status == 0:
                logger.info("tunnel_verified", protocol=protocol)
                return
            if attempt < attempts:
                await asyncio.sleep(cfg.verify_wait_sec)

        raise TunnelVerificationError(
            f"Tunnel verification failed after {attempts} attempts "
            f"(protocol={protocol}, vpn_ip={vpn_ip})"
        )

    async def stop_client(self, protocol: VpnProtocol) -> None:
        logger.info("vpn_client_stop", protocol=protocol)
        cmd = self._get_client_disconnect_cmd(protocol)
        await self._ssh.run_vm2(cmd, check=False)
        await asyncio.sleep(1)

    async def stop_server(self, protocol: VpnProtocol) -> None:
        service = self._get_server_service(protocol)
        logger.info("vpn_server_stop", protocol=protocol, service=service)
        await self._ssh.run_vm1(f"sudo systemctl stop {service}", check=False)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_server_service(self, protocol: VpnProtocol) -> str:
        match protocol:
            case VpnProtocol.WIREGUARD:
                return self._cfg.vpn.wireguard.service_name
            case VpnProtocol.OPENVPN_UDP:
                return self._cfg.vpn.openvpn_udp.service_name
            case VpnProtocol.OPENVPN_TCP:
                return self._cfg.vpn.openvpn_tcp.service_name
            case VpnProtocol.IPSEC:
                return self._cfg.vpn.ipsec.service_name
            case _:
                raise ValueError(f"Unsupported protocol: {protocol}")

    def _get_server_vpn_ip(self, protocol: VpnProtocol) -> str:
        match protocol:
            case VpnProtocol.WIREGUARD:
                return self._cfg.vpn.wireguard.server_vpn_ip
            case VpnProtocol.OPENVPN_UDP:
                return self._cfg.vpn.openvpn_udp.server_vpn_ip
            case VpnProtocol.OPENVPN_TCP:
                return self._cfg.vpn.openvpn_tcp.server_vpn_ip
            case VpnProtocol.IPSEC:
                return self._cfg.vpn.ipsec.server_vpn_ip
            case _:
                raise ValueError(f"Unsupported protocol: {protocol}")

    def _get_client_connect_cmd(self, protocol: VpnProtocol) -> str:
        match protocol:
            case VpnProtocol.WIREGUARD:
                iface = self._cfg.vpn.wireguard.client_interface
                return f"sudo wg-quick up {iface}"
            case VpnProtocol.OPENVPN_UDP:
                conf = self._cfg.vpn.openvpn_udp.client_config
                return (
                    f"sudo openvpn --config {conf} --daemon --log /tmp/ovpn-udp.log"
                )
            case VpnProtocol.OPENVPN_TCP:
                conf = self._cfg.vpn.openvpn_tcp.client_config
                return (
                    f"sudo openvpn --config {conf} --daemon --log /tmp/ovpn-tcp.log"
                )
            case VpnProtocol.IPSEC:
                conn = self._cfg.vpn.ipsec.connection_name
                return f"sudo ipsec up {conn}"
            case _:
                raise ValueError(f"Unsupported protocol: {protocol}")

    def _get_client_disconnect_cmd(self, protocol: VpnProtocol) -> str:
        match protocol:
            case VpnProtocol.WIREGUARD:
                iface = self._cfg.vpn.wireguard.client_interface
                return f"sudo wg-quick down {iface} 2>/dev/null || true"
            case VpnProtocol.OPENVPN_UDP:
                return "sudo pkill -f 'openvpn.*client-udp' || true"
            case VpnProtocol.OPENVPN_TCP:
                return "sudo pkill -f 'openvpn.*client-tcp' || true"
            case VpnProtocol.IPSEC:
                conn = self._cfg.vpn.ipsec.connection_name
                return f"sudo ipsec down {conn} 2>/dev/null || true"
            case _:
                raise ValueError(f"Unsupported protocol: {protocol}")
