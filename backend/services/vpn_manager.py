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
    def __init__(self, ssh: SshManager, *, client_vm: str = "vm2") -> None:
        self._ssh = ssh
        self._cfg = get_config()
        self._client_vm = client_vm

    async def _run_client(self, command: str, *, check: bool = True):
        if self._client_vm == "vm3":
            return await self._ssh.run_vm3(command, check=check)
        return await self._ssh.run_vm2(command, check=check)

    def _ipsec_service_action_cmd(self, action: str) -> str:
        configured = self._cfg.vpn.ipsec.service_name
        candidates = [
            configured,
            "strongswan-starter",
            "strongswan",
            "strongswan-swanctl",
        ]
        services = list(dict.fromkeys(service for service in candidates if service))
        return " || ".join(f"sudo systemctl {action} {service}" for service in services)

    # ── Public API ─────────────────────────────────────────────────────────────

    async def start_server(self, protocol: VpnProtocol) -> None:
        service = self._get_server_service(protocol)
        logger.info("vpn_server_start", protocol=protocol, service=service)
        if protocol == VpnProtocol.IPSEC:
            await self._ssh.run_vm1(self._ipsec_service_action_cmd("start"))
        elif protocol == VpnProtocol.WIREGUARD:
            iface = self._cfg.vpn.wireguard.server_interface
            await self._ssh.run_vm1(
                "sudo sed -i '/^MTU[[:space:]]*=/d' /etc/wireguard/"
                f"{iface}.conf; "
                "sudo sed -i '/^\\[Interface\\]/a MTU = 1200' /etc/wireguard/"
                f"{iface}.conf; "
                f"sudo systemctl restart {service} || "
                f"(sudo wg-quick down {iface} 2>/dev/null || true; sudo wg-quick up {iface})"
            )
        else:
            await self._ssh.run_vm1(f"sudo systemctl start {service}")
        await asyncio.sleep(1)  # Give service a moment to bind

    async def start_client(self, protocol: VpnProtocol) -> None:
        logger.info("vpn_client_start", protocol=protocol)
        cmd = self._get_client_connect_cmd(protocol)
        await self._run_client(cmd)
        await asyncio.sleep(1.5)

    async def verify_tunnel(self, protocol: VpnProtocol) -> None:
        """Ping VM1's VPN IP from the selected client VM. Retries up to verify_max_attempts."""
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
            result = await self._run_client(
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
        await self._run_client(cmd, check=False)
        await asyncio.sleep(1)

    async def stop_server(self, protocol: VpnProtocol) -> None:
        service = self._get_server_service(protocol)
        logger.info("vpn_server_stop", protocol=protocol, service=service)
        if protocol == VpnProtocol.IPSEC:
            await self._ssh.run_vm1(self._ipsec_service_action_cmd("stop"), check=False)
        else:
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
                server_ip = self._cfg.vpn.wireguard.server_vpn_ip
                # Bring down first in case it's already up from a previous unclean run
                return (
                    "sudo sed -i '/^MTU[[:space:]]*=/d' /etc/wireguard/"
                    f"{iface}.conf; "
                    "sudo sed -i '/^\\[Interface\\]/a MTU = 1200' /etc/wireguard/"
                    f"{iface}.conf; "
                    f"sudo wg-quick down {iface} 2>/dev/null || true; "
                    f"sudo wg-quick up {iface}; "
                    f"ping -c 1 -W 2 {server_ip} >/dev/null 2>&1 || true"
                )
            case VpnProtocol.OPENVPN_UDP:
                conf = self._cfg.vpn.openvpn_udp.client_config
                return self._openvpn_client_cmd(conf, "/tmp/ovpn-udp.log")
            case VpnProtocol.OPENVPN_TCP:
                conf = self._cfg.vpn.openvpn_tcp.client_config
                return self._openvpn_client_cmd(conf, "/tmp/ovpn-tcp.log")
            case VpnProtocol.IPSEC:
                conn = self._cfg.vpn.ipsec.connection_name
                server_ip = self._cfg.vpn.ipsec.server_vpn_ip
                client_ip = self._cfg.vpn.ipsec.client_vpn_ip
                iface = self._get_client_network_interface()
                return (
                    f"sudo ipsec up {conn}; "
                    f"sudo ip route replace {server_ip}/32 dev {iface} src {client_ip}"
                )
            case _:
                raise ValueError(f"Unsupported protocol: {protocol}")

    def _get_client_network_interface(self) -> str:
        if self._client_vm == "vm3" and self._cfg.infrastructure.vm3 is not None:
            return self._cfg.infrastructure.vm3.network_interface or "tailscale0"
        return self._cfg.infrastructure.vm2.network_interface or "tailscale0"

    def _openvpn_client_cmd(self, conf: str, log_path: str) -> str:
        client_dir = "/etc/openvpn/client"
        required = [
            conf,
            f"{client_dir}/ca.crt",
            f"{client_dir}/vpn-client.crt",
            f"{client_dir}/vpn-client.key",
            f"{client_dir}/ta.key",
        ]
        checks = " && ".join(f"sudo test -r {path}" for path in required)
        return (
            f"({checks}) || "
            f"(echo 'OpenVPN client config/cert files missing under {client_dir}' >&2; "
            f"sudo ls -la {client_dir} >&2; exit 1); "
            "sudo pkill -x openvpn 2>/dev/null || true; "
            "sudo ip link del tun0 2>/dev/null || true; "
            "sudo ip link del tun1 2>/dev/null || true; "
            "sleep 1; "
            f"sudo rm -f {log_path}; "
            f"sudo /usr/sbin/openvpn --config {conf} --daemon --log {log_path} || "
            f"(sudo test -r {log_path} && sudo tail -n 80 {log_path} >&2; exit 1); "
            f"sleep 1; "
            f"if sudo grep -Eiq 'Options error|Cannot|ERROR|Exiting|AUTH_FAILED|TLS Error' {log_path}; "
            f"then sudo tail -n 80 {log_path} >&2; exit 1; fi"
        )

    def _get_client_disconnect_cmd(self, protocol: VpnProtocol) -> str:
        match protocol:
            case VpnProtocol.WIREGUARD:
                iface = self._cfg.vpn.wireguard.client_interface
                return f"sudo wg-quick down {iface} 2>/dev/null || true"
            case VpnProtocol.OPENVPN_UDP:
                return "sudo pkill -x openvpn 2>/dev/null || true"
            case VpnProtocol.OPENVPN_TCP:
                return "sudo pkill -x openvpn 2>/dev/null || true"
            case VpnProtocol.IPSEC:
                conn = self._cfg.vpn.ipsec.connection_name
                server_ip = self._cfg.vpn.ipsec.server_vpn_ip
                return (
                    f"sudo ip route del {server_ip}/32 2>/dev/null || true; "
                    f"sudo ipsec down {conn} 2>/dev/null || true"
                )
            case _:
                raise ValueError(f"Unsupported protocol: {protocol}")
