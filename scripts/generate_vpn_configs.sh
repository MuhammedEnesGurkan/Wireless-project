#!/usr/bin/env bash
# =============================================================================
# generate_vpn_configs.sh
# =============================================================================
# Exchanges public keys between VM1 and VM2 over SSH and regenerates
# WireGuard configs so the peers know each other.
#
# Run from the HOST machine AFTER setup_vm1.sh and setup_vm2.sh have completed.
#
# Prerequisites:
#   - SSH access to VM1 and VM2 via the key configured in config.yaml
#   - jq installed on host (for JSON helpers)
#
# Usage:
#   chmod +x generate_vpn_configs.sh
#   bash generate_vpn_configs.sh
# =============================================================================

set -euo pipefail

# ── Override these via environment or .env.example ────────────────────────────
VM1_HOST="${VM1_HOST:-100.70.73.68}"
VM1_USER="${VM1_USER:-wazuh}"
VM1_PORT="${VM1_PORT:-22}"

VM2_HOST="${VM2_HOST:-100.101.234.82}"
VM2_USER="${VM2_USER:-sshka}"
VM2_PORT="${VM2_PORT:-22}"

VM3_HOST="${VM3_HOST-100.85.164.55}"
VM3_USER="${VM3_USER:-agurk}"
VM3_PORT="${VM3_PORT:-22}"

SSH_KEY="${SSH_KEY:-~/.ssh/vpn_bench_key}"

WG_PORT="${WG_PORT:-51820}"
WG_SERVER_ADDR="${WG_SERVER_ADDR:-10.200.0.1/24}"
WG_CLIENT_ADDR="${WG_CLIENT_ADDR:-10.200.0.2/24}"
WG_CLIENT_IP_ONLY="${WG_CLIENT_IP_ONLY:-10.200.0.2/32}"

IFACE="${IFACE:-tailscale0}"

# ── SSH helpers ───────────────────────────────────────────────────────────────
ssh_vm1() { ssh -i "${SSH_KEY}" -p "${VM1_PORT}" -o StrictHostKeyChecking=no "${VM1_USER}@${VM1_HOST}" "$@"; }
ssh_vm2() { ssh -i "${SSH_KEY}" -p "${VM2_PORT}" -o StrictHostKeyChecking=no "${VM2_USER}@${VM2_HOST}" "$@"; }
ssh_vm3() { ssh -i "${SSH_KEY}" -p "${VM3_PORT}" -o StrictHostKeyChecking=no "${VM3_USER}@${VM3_HOST}" "$@"; }

info()  { echo -e "\033[0;32m[INFO]\033[0m  $*"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

# ── 1. Collect public keys ─────────────────────────────────────────────────────
collect_keys() {
  info "Fetching VM1 WireGuard public key…"
  VM1_WG_PUB=$(ssh_vm1 "sudo cat /etc/wireguard/server_public.key")
  info "VM1 pubkey: ${VM1_WG_PUB}"

  info "Fetching VM2 WireGuard public key…"
  VM2_WG_PUB=$(ssh_vm2 "sudo cat /etc/wireguard/client_public.key")
  info "VM2 pubkey: ${VM2_WG_PUB}"
}

# ── 2. Write WireGuard configs ─────────────────────────────────────────────────
configure_wireguard() {
  info "Writing WireGuard server config on VM1…"
  VM1_PRIVKEY=$(ssh_vm1 "sudo cat /etc/wireguard/server_private.key")

  ssh_vm1 "sudo tee /etc/wireguard/wg0.conf > /dev/null" <<WG_CONF
[Interface]
Address    = ${WG_SERVER_ADDR}
ListenPort = ${WG_PORT}
PrivateKey = ${VM1_PRIVKEY}
PostUp   = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ${IFACE} -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ${IFACE} -j MASQUERADE

[Peer]
PublicKey  = ${VM2_WG_PUB}
AllowedIPs = ${WG_CLIENT_IP_ONLY}
WG_CONF

  info "Writing WireGuard client config on VM2…"
  VM2_PRIVKEY=$(ssh_vm2 "sudo cat /etc/wireguard/client_private.key")

  ssh_vm2 "sudo tee /etc/wireguard/wg0.conf > /dev/null" <<WG_CONF
[Interface]
Address    = ${WG_CLIENT_ADDR}
PrivateKey = ${VM2_PRIVKEY}

[Peer]
PublicKey  = ${VM1_WG_PUB}
Endpoint   = ${VM1_HOST}:${WG_PORT}
AllowedIPs = 10.200.0.0/24
PersistentKeepalive = 25
WG_CONF

  ssh_vm1 "sudo chmod 600 /etc/wireguard/wg0.conf"
  ssh_vm2 "sudo chmod 600 /etc/wireguard/wg0.conf"
  info "WireGuard configs exchanged ✓"
}

# ── 3. Copy OpenVPN client certs from VM1 to VM2 ─────────────────────────────
distribute_openvpn_certs() {
  info "Copying OpenVPN certificates from VM1 to client nodes…"
  TMPDIR_HOST=$(mktemp -d)

  ssh_vm1 "sudo tar -czf /tmp/ovpn-client-certs.tar.gz \
    /etc/openvpn/client/ca.crt \
    /etc/openvpn/client/vpn-client.crt \
    /etc/openvpn/client/vpn-client.key \
    /etc/openvpn/client/ta.key 2>/dev/null"

  scp -i "${SSH_KEY}" -P "${VM1_PORT}" \
    "${VM1_USER}@${VM1_HOST}:/tmp/ovpn-client-certs.tar.gz" \
    "${TMPDIR_HOST}/ovpn-client-certs.tar.gz"

  copy_openvpn_bundle_to_client "${VM2_HOST}" "${VM2_USER}" "${VM2_PORT}" "VM2"

  if [[ -n "${VM3_HOST}" ]]; then
    copy_openvpn_bundle_to_client "${VM3_HOST}" "${VM3_USER}" "${VM3_PORT}" "VM3"
  fi

  rm -rf "${TMPDIR_HOST}"
  info "OpenVPN certs distributed ✓"
}

copy_openvpn_bundle_to_client() {
  local host="$1"
  local user="$2"
  local port="$3"
  local label="$4"

  info "Copying OpenVPN client certs to ${label}..."
  scp -i "${SSH_KEY}" -P "${port}" \
    "${TMPDIR_HOST}/ovpn-client-certs.tar.gz" \
    "${user}@${host}:/tmp/"

  ssh -i "${SSH_KEY}" -p "${port}" -o StrictHostKeyChecking=no "${user}@${host}" \
    "sudo mkdir -p /etc/openvpn/client && \
     sudo tar -xzf /tmp/ovpn-client-certs.tar.gz -C / && \
     sudo chmod 600 /etc/openvpn/client/*.key"
}

# ── 4. Copy IPSec CA cert from VM1 to VM2 ────────────────────────────────────
distribute_ipsec_ca() {
  info "Copying IPSec CA cert from VM1 to client nodes…"
  TMPDIR_HOST=$(mktemp -d)

  scp -i "${SSH_KEY}" -P "${VM1_PORT}" \
    "${VM1_USER}@${VM1_HOST}:/etc/ipsec.d/cacerts/ca.cert.pem" \
    "${TMPDIR_HOST}/ca.cert.pem"

  copy_ipsec_ca_to_client "${VM2_HOST}" "${VM2_USER}" "${VM2_PORT}" "VM2"

  if [[ -n "${VM3_HOST}" ]]; then
    copy_ipsec_ca_to_client "${VM3_HOST}" "${VM3_USER}" "${VM3_PORT}" "VM3"
  fi

  rm -rf "${TMPDIR_HOST}"
  info "IPSec CA distributed ✓"
}

copy_ipsec_ca_to_client() {
  local host="$1"
  local user="$2"
  local port="$3"
  local label="$4"

  info "Copying IPSec CA to ${label}..."
  scp -i "${SSH_KEY}" -P "${port}" \
    "${TMPDIR_HOST}/ca.cert.pem" \
    "${user}@${host}:/tmp/"

  ssh -i "${SSH_KEY}" -p "${port}" -o StrictHostKeyChecking=no "${user}@${host}" \
    "sudo mkdir -p /etc/ipsec.d/cacerts && \
     sudo mv /tmp/ca.cert.pem /etc/ipsec.d/cacerts/ && \
     sudo ipsec reload 2>/dev/null || true"
}

# ── 5. Quick smoke test ───────────────────────────────────────────────────────
smoke_test() {
  info "Running smoke test — starting WireGuard on both VMs…"
  ssh_vm1 "sudo systemctl restart wg-quick@wg0 2>/dev/null || sudo wg-quick up wg0"
  sleep 2
  ssh_vm2 "sudo wg-quick up wg0 2>/dev/null || true"
  sleep 2

  info "Pinging VM1 WireGuard IP from VM2…"
  if ssh_vm2 "ping -c 3 -W 3 10.200.0.1" &>/dev/null; then
    info "WireGuard tunnel working ✓"
  else
    echo "[WARN] WireGuard ping failed — check firewall / routing."
  fi

  ssh_vm2 "sudo wg-quick down wg0 2>/dev/null || true"
  ssh_vm1 "sudo systemctl stop wg-quick@wg0 2>/dev/null || true"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  collect_keys
  configure_wireguard
  distribute_openvpn_certs
  distribute_ipsec_ca
  smoke_test

  info "================================================="
  info "VPN configs generated and distributed!"
  info "You can now start the backend and open the UI."
  info "================================================="
}

main "$@"
