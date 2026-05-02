#!/usr/bin/env bash
# =============================================================================
# check_setup.sh — VPN Benchmark setup verification for VM1 / VM2
# =============================================================================
# Usage:
#   sudo bash check_setup.sh --vm1
#   sudo bash check_setup.sh --vm2
#
# Optional overrides:
#   VM1_IP=192.168.80.141 VM2_IP=192.168.80.145 IFACE=ens33 sudo bash check_setup.sh --vm2
# =============================================================================

set -euo pipefail

VM1_IP="${VM1_IP:-192.168.80.141}"
VM2_IP="${VM2_IP:-192.168.80.145}"
IFACE="${IFACE:-ens33}"

ROLE="${1:-}"
if [[ "${ROLE}" != "--vm1" && "${ROLE}" != "--vm2" ]]; then
  echo "Usage: sudo bash $0 --vm1|--vm2"
  exit 1
fi

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "[PASS] $*"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "[FAIL] $*"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

check_cmd() {
  local cmd="$1"
  local label="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    pass "${label}"
  else
    fail "${label}"
  fi
}

check_file() {
  local file="$1"
  local label="$2"
  if [[ -f "${file}" ]]; then
    pass "${label}"
  else
    fail "${label}"
  fi
}

check_contains() {
  local file="$1"
  local needle="$2"
  local label="$3"
  if [[ -f "${file}" ]] && grep -Fq "${needle}" "${file}"; then
    pass "${label}"
  else
    fail "${label}"
  fi
}

check_service_enabled() {
  local svc="$1"
  local label="$2"
  if systemctl is-enabled "${svc}" >/dev/null 2>&1; then
    pass "${label}"
  else
    fail "${label}"
  fi
}

check_sudoers() {
  local sudo_user="${SUDO_USER:-${USER}}"
  if [[ -f /etc/sudoers.d/vpn-bench ]] && grep -Fq "${sudo_user} ALL=(ALL) NOPASSWD: ALL" /etc/sudoers.d/vpn-bench; then
    pass "sudoers entry exists for ${sudo_user}"
  else
    fail "sudoers entry missing for ${sudo_user}"
  fi
}

check_common() {
  check_cmd wg "wireguard tools installed (wg)"
  check_cmd iperf3 "iperf3 installed"
  check_cmd ip "iproute2 installed (ip)"
  check_file /etc/wireguard/wg0.conf "WireGuard config exists"
  check_file /etc/sudoers.d/vpn-bench "sudoers drop-in exists"
  check_sudoers
}

check_vm1() {
  echo "== Checking VM1 setup =="
  check_common
  check_cmd openvpn "openvpn installed"
  check_cmd ipsec "strongSwan installed (ipsec)"
  check_file /etc/openvpn/server/server-udp.conf "OpenVPN UDP server config exists"
  check_file /etc/openvpn/server/server-tcp.conf "OpenVPN TCP server config exists"
  check_file /etc/ipsec.conf "IPSec config exists"
  check_file /etc/ipsec.secrets "IPSec secrets exists"
  check_contains /etc/wireguard/wg0.conf "Address = 10.200.0.1/24" "WireGuard server address set"
  check_contains /etc/ipsec.conf "leftid=${VM1_IP}" "IPSec leftid matches VM1 IP (${VM1_IP})"
  check_service_enabled wg-quick@wg0 "wg-quick@wg0 enabled"
  check_service_enabled openvpn-server@server-udp "OpenVPN UDP service enabled"
  check_service_enabled openvpn-server@server-tcp "OpenVPN TCP service enabled"
  if systemctl list-unit-files | grep -q '^strongswan-starter\.service'; then
    check_service_enabled strongswan-starter "strongSwan starter service enabled"
  elif systemctl list-unit-files | grep -q '^strongswan\.service'; then
    check_service_enabled strongswan "strongSwan service enabled"
  elif systemctl list-unit-files | grep -q '^strongswan-swanctl\.service'; then
    check_service_enabled strongswan-swanctl "strongSwan swanctl service enabled"
  else
    fail "No strongSwan systemd unit found (starter/strongswan/swanctl)"
  fi
}

check_vm2() {
  echo "== Checking VM2 setup =="
  check_common
  check_cmd openvpn "openvpn installed"
  check_cmd ipsec "strongSwan installed (ipsec)"
  check_cmd tc "tc installed"
  check_cmd hping3 "hping3 installed"
  check_file /etc/openvpn/client/client-udp.conf "OpenVPN UDP client config exists"
  check_file /etc/openvpn/client/client-tcp.conf "OpenVPN TCP client config exists"
  check_file /etc/ipsec.conf "IPSec config exists"
  check_file /etc/ipsec.secrets "IPSec secrets exists"
  check_contains /etc/wireguard/wg0.conf "Endpoint   = ${VM1_IP}:51820" "WireGuard endpoint points VM1 (${VM1_IP})"
  check_contains /etc/ipsec.conf "right=${VM1_IP}" "IPSec right host matches VM1 IP (${VM1_IP})"
  if tc qdisc show dev "${IFACE}" >/dev/null 2>&1; then
    pass "tc qdisc accessible on ${IFACE}"
  else
    fail "tc qdisc not accessible on ${IFACE}"
  fi
}

if [[ "${ROLE}" == "--vm1" ]]; then
  check_vm1
else
  check_vm2
fi

echo
echo "Summary: PASS=${PASS_COUNT} FAIL=${FAIL_COUNT}"
if [[ ${FAIL_COUNT} -gt 0 ]]; then
  exit 1
fi
