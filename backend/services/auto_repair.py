"""
Infrastructure health checks and safe auto-fixes for the benchmark VMs.

The repair runner intentionally focuses on idempotent setup items: package
installation, strongSwan plugin/config fixes, CA distribution, IPsec route
helper, and benchmark firewall/iperf prerequisites. VPN key regeneration for
WireGuard/OpenVPN is reported but not silently recreated.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

from backend.core.config import get_config
from backend.models.schemas import VpnProtocol
from backend.services.ssh_manager import SshManager


@dataclass
class RepairItem:
    vm: str
    protocol: str
    check: str
    ok: bool
    message: str
    fixed: bool = False


@dataclass
class AutoRepairReport:
    apply_fixes: bool
    items: list[RepairItem] = field(default_factory=list)

    def add(
        self,
        *,
        vm: str,
        protocol: str,
        check: str,
        ok: bool,
        message: str,
        fixed: bool = False,
    ) -> None:
        self.items.append(
            RepairItem(
                vm=vm,
                protocol=protocol,
                check=check,
                ok=ok,
                message=message,
                fixed=fixed,
            )
        )

    def model_dump(self) -> dict:
        total = len(self.items)
        failed = len([item for item in self.items if not item.ok and not item.fixed])
        fixed = len([item for item in self.items if item.fixed])
        return {
            "apply_fixes": self.apply_fixes,
            "summary": {
                "total": total,
                "ok": total - failed,
                "failed": failed,
                "fixed": fixed,
            },
            "items": [item.__dict__ for item in self.items],
        }


class AutoRepairManager:
    def __init__(self, ssh: SshManager) -> None:
        self._ssh = ssh
        self._cfg = get_config()

    async def run(self, *, apply_fixes: bool = False) -> AutoRepairReport:
        report = AutoRepairReport(apply_fixes=apply_fixes)
        clients = ["vm2"]
        if self._cfg.infrastructure.vm3 is not None:
            clients.append("vm3")

        await self._check_vm1_common(report, apply_fixes=apply_fixes)
        for client in clients:
            await self._check_client_common(client, report, apply_fixes=apply_fixes)

        for protocol in [
            VpnProtocol.WIREGUARD,
            VpnProtocol.OPENVPN_UDP,
            VpnProtocol.OPENVPN_TCP,
            VpnProtocol.IPSEC,
        ]:
            await self._check_protocol(protocol, clients, report, apply_fixes=apply_fixes)

        return report

    async def _run(self, vm: str, command: str, *, check: bool = False):
        if vm == "vm1":
            return await self._ssh.run_vm1(command, check=check)
        if vm == "vm2":
            return await self._ssh.run_vm2(command, check=check)
        return await self._ssh.run_vm3(command, check=check)

    async def _check_cmd(
        self,
        vm: str,
        command: str,
        report: AutoRepairReport,
        *,
        protocol: str = "common",
        check: str,
        fix: str | None = None,
        apply_fixes: bool,
        ok_message: str,
        fail_message: str,
    ) -> None:
        result = await self._run(vm, command)
        if result.exit_status == 0:
            report.add(vm=vm, protocol=protocol, check=check, ok=True, message=ok_message)
            return
        if apply_fixes and fix:
            fix_result = await self._run(vm, fix)
            if fix_result.exit_status == 0:
                report.add(
                    vm=vm,
                    protocol=protocol,
                    check=check,
                    ok=True,
                    message=f"{fail_message} Fixed.",
                    fixed=True,
                )
                return
        report.add(vm=vm, protocol=protocol, check=check, ok=False, message=fail_message)

    async def _check_vm1_common(self, report: AutoRepairReport, *, apply_fixes: bool) -> None:
        install = (
            "sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "
            "wireguard openvpn easy-rsa strongswan strongswan-pki libcharon-extra-plugins "
            "libcharon-extauth-plugins libstrongswan-standard-plugins libstrongswan-extra-plugins "
            "iperf3 iproute2 iputils-ping"
        )
        await self._check_cmd(
            "vm1",
            "command -v iperf3 >/dev/null && command -v ipsec >/dev/null",
            report,
            check="packages",
            fix=install,
            apply_fixes=apply_fixes,
            ok_message="Required server packages are installed.",
            fail_message="Missing server packages.",
        )
        if apply_fixes:
            await self._run(
                "vm1",
                "sudo iptables -I INPUT -s 10.10.0.0/24 -p icmp -j ACCEPT 2>/dev/null || true; "
                "sudo iptables -I INPUT -s 10.10.0.0/24 -p tcp --dport 5201 -j ACCEPT 2>/dev/null || true; "
                "sudo iptables -I INPUT -p udp --dport 500 -j ACCEPT 2>/dev/null || true; "
                "sudo iptables -I INPUT -p udp --dport 4500 -j ACCEPT 2>/dev/null || true; "
                "sudo ip link add ipsec0 type dummy 2>/dev/null || true; "
                "sudo ip addr replace 10.10.0.1/24 dev ipsec0; sudo ip link set ipsec0 up",
            )
            report.add(
                vm="vm1",
                protocol="common",
                check="firewall_ipsec0",
                ok=True,
                message="Applied VM1 firewall rules and ipsec0 address.",
                fixed=True,
            )

    async def _check_client_common(
        self,
        vm: str,
        report: AutoRepairReport,
        *,
        apply_fixes: bool,
    ) -> None:
        install = (
            "sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "
            "wireguard openvpn strongswan libcharon-extra-plugins libcharon-extauth-plugins "
            "libstrongswan-standard-plugins libstrongswan-extra-plugins iperf3 hping3 "
            "iproute2 iputils-ping"
        )
        await self._check_cmd(
            vm,
            "command -v iperf3 >/dev/null && command -v ipsec >/dev/null && command -v tc >/dev/null",
            report,
            check="packages",
            fix=install,
            apply_fixes=apply_fixes,
            ok_message="Required client packages are installed.",
            fail_message="Missing client packages.",
        )

    async def _check_protocol(
        self,
        protocol: VpnProtocol,
        clients: list[str],
        report: AutoRepairReport,
        *,
        apply_fixes: bool,
    ) -> None:
        if protocol == VpnProtocol.WIREGUARD:
            await self._check_wireguard(clients, report)
        elif protocol in (VpnProtocol.OPENVPN_UDP, VpnProtocol.OPENVPN_TCP):
            await self._check_openvpn(protocol, clients, report, apply_fixes=apply_fixes)
        elif protocol == VpnProtocol.IPSEC:
            await self._check_ipsec(clients, report, apply_fixes=apply_fixes)

    async def _check_wireguard(self, clients: list[str], report: AutoRepairReport) -> None:
        await self._check_cmd(
            "vm1",
            "sudo test -r /etc/wireguard/wg0.conf",
            report,
            protocol="wireguard",
            check="server_config",
            apply_fixes=False,
            ok_message="WireGuard server config exists.",
            fail_message="WireGuard server config missing. Run setup/generate scripts.",
        )
        for vm in clients:
            await self._check_cmd(
                vm,
                "sudo test -r /etc/wireguard/wg0.conf",
                report,
                protocol="wireguard",
                check="client_config",
                apply_fixes=False,
                ok_message="WireGuard client config exists.",
                fail_message="WireGuard client config missing. Run setup/generate scripts.",
            )

    async def _check_openvpn(
        self,
        protocol: VpnProtocol,
        clients: list[str],
        report: AutoRepairReport,
        *,
        apply_fixes: bool,
    ) -> None:
        server_conf = (
            self._cfg.vpn.openvpn_udp.server_config
            if protocol == VpnProtocol.OPENVPN_UDP
            else self._cfg.vpn.openvpn_tcp.server_config
        )
        client_conf = (
            self._cfg.vpn.openvpn_udp.client_config
            if protocol == VpnProtocol.OPENVPN_UDP
            else self._cfg.vpn.openvpn_tcp.client_config
        )
        proto = "udp" if protocol == VpnProtocol.OPENVPN_UDP else "tcp"
        await self._check_cmd(
            "vm1",
            f"sudo test -r {server_conf}",
            report,
            protocol=protocol.value,
            check="server_config",
            apply_fixes=False,
            ok_message="OpenVPN server config exists.",
            fail_message="OpenVPN server config missing. Run setup/generate scripts.",
        )
        bundle = await self._read_openvpn_client_bundle()
        for vm in clients:
            fix = self._openvpn_client_fix_cmd(proto, bundle) if bundle else None
            await self._check_cmd(
                vm,
                f"sudo test -r {client_conf} && sudo test -r /etc/openvpn/client/ca.crt",
                report,
                protocol=protocol.value,
                check="client_config_certs",
                fix=fix,
                apply_fixes=apply_fixes,
                ok_message="OpenVPN client config/certs exist.",
                fail_message=(
                    "OpenVPN client config/certs missing. VM1 client bundle is available for auto-fix." if fix else
                    "OpenVPN client config/certs missing. Run generate_vpn_configs.sh."
                ),
            )

    async def _read_openvpn_client_bundle(self) -> dict[str, str]:
        files = {
            "ca.crt": "/etc/openvpn/client/ca.crt",
            "vpn-client.crt": "/etc/openvpn/client/vpn-client.crt",
            "vpn-client.key": "/etc/openvpn/client/vpn-client.key",
            "ta.key": "/etc/openvpn/client/ta.key",
        }
        bundle: dict[str, str] = {}
        for name, path in files.items():
            result = await self._run("vm1", f"sudo base64 -w0 {path}")
            if result.exit_status != 0 or not (result.stdout or "").strip():
                return {}
            bundle[name] = (result.stdout or "").strip()
        return bundle

    def _openvpn_client_fix_cmd(self, proto: str, bundle: dict[str, str]) -> str:
        vm1_host = self._cfg.infrastructure.vm1.host
        dev = "tun" if proto == "udp" else "tun"
        conf_name = f"client-{proto}.conf"
        return (
            "sudo mkdir -p /etc/openvpn/client; "
            + " ".join(
                f"echo {data} | sudo base64 -d > /tmp/{name}; "
                f"sudo mv /tmp/{name} /etc/openvpn/client/{name}; "
                for name, data in bundle.items()
            )
            + "sudo chmod 600 /etc/openvpn/client/*.key; "
            + f"printf 'client\\ndev {dev}\\nproto {proto}\\nremote {vm1_host} 1194\\n"
            "resolv-retry infinite\\nnobind\\npersist-key\\npersist-tun\\n"
            "ca /etc/openvpn/client/ca.crt\\n"
            "cert /etc/openvpn/client/vpn-client.crt\\n"
            "key /etc/openvpn/client/vpn-client.key\\n"
            "tls-auth /etc/openvpn/client/ta.key 1\\n"
            "cipher AES-256-GCM\\nauth SHA256\\ncompress lz4-v2\\nverb 3\\n' "
            f"| sudo tee /etc/openvpn/client/{conf_name} >/dev/null"
        )

    async def _check_ipsec(
        self,
        clients: list[str],
        report: AutoRepairReport,
        *,
        apply_fixes: bool,
    ) -> None:
        await self._check_cmd(
            "vm1",
            "sudo ipsec statusall | grep -q eap-mschapv2 && "
            "sudo ipsec pki --print --in /etc/ipsec.d/certs/server.cert.pem 2>/dev/null | "
            f"grep -q {self._cfg.infrastructure.vm1.host}",
            report,
            protocol="ipsec",
            check="server_plugins_cert",
            apply_fixes=False,
            ok_message="IPsec server plugins and certificate look good.",
            fail_message="IPsec server plugin/certificate mismatch. Run scripts/fix_ipsec_tailscale.sh --vm1.",
        )
        ca_result = await self._run("vm1", "sudo base64 -w0 /etc/ipsec.d/cacerts/ca.cert.pem")
        ca_b64 = (ca_result.stdout or "").strip() if ca_result.exit_status == 0 else ""
        for vm in clients:
            await self._fix_ipsec_client(vm, ca_b64, report, apply_fixes=apply_fixes)

    async def _fix_ipsec_client(
        self,
        vm: str,
        ca_b64: str,
        report: AutoRepairReport,
        *,
        apply_fixes: bool,
    ) -> None:
        if vm == "vm3" and self._cfg.infrastructure.vm3 is not None:
            iface = self._cfg.infrastructure.vm3.network_interface or "tailscale0"
        else:
            iface = self._cfg.infrastructure.vm2.network_interface or "tailscale0"
        server_ip = self._cfg.vpn.ipsec.server_vpn_ip
        client_ip = self._cfg.vpn.ipsec.client_vpn_ip
        vm1_host = self._cfg.infrastructure.vm1.host
        conn = self._cfg.vpn.ipsec.connection_name
        ike = self._cfg.vpn.ipsec.ike_proposal
        esp = self._cfg.vpn.ipsec.esp_proposal
        check = (
            "sudo test -r /etc/ipsec.d/cacerts/ca.cert.pem && "
            "sudo ipsec statusall | grep -q eap-mschapv2 && "
            "sudo test -x /usr/local/sbin/vpnbench-ipsec-route"
        )
        fix = (
            "sudo mkdir -p /etc/ipsec.d/cacerts /etc/strongswan.d/charon; "
            f"echo {ca_b64} | sudo base64 -d > /tmp/ca.cert.pem; "
            "sudo mv /tmp/ca.cert.pem /etc/ipsec.d/cacerts/ca.cert.pem; "
            "sudo chmod 644 /etc/ipsec.d/cacerts/ca.cert.pem; "
            "printf 'openssl {\\n    load = yes\\n}\\n' | sudo tee /etc/strongswan.d/charon/openssl.conf >/dev/null; "
            "printf 'eap-mschapv2 {\\n    load = yes\\n}\\n' | sudo tee /etc/strongswan.d/charon/eap-mschapv2.conf >/dev/null; "
            "printf 'charon {\\n    load_modular = yes\\n    plugins {\\n        include strongswan.d/charon/*.conf\\n    }\\n}\\ninclude strongswan.d/*.conf\\n' "
            "| sudo tee /etc/strongswan.conf >/dev/null; "
            f"printf 'config setup\\n    charondebug=\"ike 2, knl 1, cfg 2\"\\n\\nconn {conn}\\n    auto=add\\n    keyexchange=ikev2\\n    type=tunnel\\n    fragmentation=yes\\n    forceencaps=yes\\n    rekey=no\\n    left=%any\\n    leftid=vpnbench\\n    leftauth=eap-mschapv2\\n    leftsourceip=%config\\n    right={vm1_host}\\n    rightid={vm1_host}\\n    rightsubnet=0.0.0.0/0\\n    rightauth=pubkey\\n    eap_identity=vpnbench\\n    aaa_identity=%any\\n    ike={ike}!\\n    esp={esp}!\\n' "
            "| sudo tee /etc/ipsec.conf >/dev/null; "
            "printf 'vpnbench : EAP \"changeme_strong_password\"\\n' | sudo tee /etc/ipsec.secrets >/dev/null; "
            "sudo chmod 600 /etc/ipsec.secrets; "
            f"printf '#!/usr/bin/env bash\\nset -euo pipefail\\nip route replace {server_ip}/32 dev {iface} src {client_ip}\\n' "
            "| sudo tee /usr/local/sbin/vpnbench-ipsec-route >/dev/null; "
            "sudo chmod 755 /usr/local/sbin/vpnbench-ipsec-route; "
            "sudo systemctl restart strongswan-starter 2>/dev/null || sudo systemctl restart strongswan 2>/dev/null || sudo ipsec restart"
        )
        await self._check_cmd(
            vm,
            check,
            report,
            protocol="ipsec",
            check="client_ca_plugins_route",
            fix=fix if ca_b64 else None,
            apply_fixes=apply_fixes,
            ok_message="IPsec client CA/plugins/route helper exist.",
            fail_message="IPsec client CA/plugins/route helper missing.",
        )
