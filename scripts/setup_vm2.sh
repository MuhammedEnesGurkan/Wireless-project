#!/usr/bin/env bash
# =============================================================================
# setup_vm2.sh — VPN Benchmark Suite: VM2 (Client + Test Engine) Setup
# =============================================================================
# Run once on VM2 (Ubuntu 22.04 / 24.04) to install:
#   • WireGuard client
#   • OpenVPN client
#   • strongSwan (IPSec client)
#   • iperf3
#   • hping3
#   • iproute2 / tc (netem)
#   • ping (iputils-ping)
#
# Usage:
#   chmod +x setup_vm2.sh
#   sudo bash setup_vm2.sh
# =============================================================================

set -euo pipefail

VM1_IP="${VM1_IP:-100.70.73.68}"
IFACE="${IFACE:-tailscale0}"
KEY_DIR="${KEY_DIR:-/etc/vpn-bench/keys}"
OVPN_CLIENT_DIR="${OVPN_CLIENT_DIR:-/etc/openvpn/client}"
WG_PORT="${WG_PORT:-51820}"

info()  { echo -e "\033[0;32m[INFO]\033[0m  $*"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

require_root() {
  [[ $EUID -eq 0 ]] || error "Please run as root (sudo bash $0)"
}

# ── 0. Passwordless sudo for SSH automation ──────────────────────────────────
configure_sudoers() {
  info "Configuring passwordless sudo for SSH automation…"
  SSH_USER="${SUDO_USER:-$USER}"
  echo "${SSH_USER} ALL=(ALL) NOPASSWD: ALL" | tee /etc/sudoers.d/vpn-bench > /dev/null
  chmod 440 /etc/sudoers.d/vpn-bench
  info "Sudoers configured for ${SSH_USER} ✓"
}

# ── 1. System update + packages ───────────────────────────────────────────────
install_packages() {
  info "Updating package lists…"
  apt-get update -qq

  info "Installing packages…"
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    wireguard     \
    openvpn       \
    strongswan    \
    iperf3        \
    hping3        \
    iproute2      \
    iputils-ping  \
    net-tools     \
    curl
}

# ── 2. WireGuard client interface ─────────────────────────────────────────────
setup_wireguard_client() {
  info "Generating WireGuard client keys…"
  mkdir -p /etc/wireguard
  chmod 700 /etc/wireguard

  wg genkey | tee /etc/wireguard/client_private.key | wg pubkey > /etc/wireguard/client_public.key
  chmod 600 /etc/wireguard/client_private.key

  CLIENT_PRIVKEY=$(cat /etc/wireguard/client_private.key)

  # Server pubkey is filled in after generate_vpn_configs.sh runs
  SERVER_PUBKEY="${SERVER_PUBKEY:-PLACEHOLDER_SERVER_PUBKEY}"

  cat > /etc/wireguard/wg0.conf <<WG_CONF
[Interface]
Address    = 10.200.0.2/24
PrivateKey = ${CLIENT_PRIVKEY}

[Peer]
PublicKey  = ${SERVER_PUBKEY}
Endpoint   = ${VM1_IP}:${WG_PORT}
AllowedIPs = 10.200.0.0/24
PersistentKeepalive = 25
WG_CONF

  chmod 600 /etc/wireguard/wg0.conf
  info "WireGuard client configured ✓"
}

# ── 3. OpenVPN client configs ─────────────────────────────────────────────────
setup_openvpn_client() {
  info "Setting up OpenVPN client configs…"
  mkdir -p "${OVPN_CLIENT_DIR}"

  cat > "${OVPN_CLIENT_DIR}/client-udp.conf" <<EOF
client
dev tun
proto udp
remote ${VM1_IP} 1194
resolv-retry infinite
nobind
persist-key
persist-tun
ca   ${OVPN_CLIENT_DIR}/ca.crt
cert ${OVPN_CLIENT_DIR}/vpn-client.crt
key  ${OVPN_CLIENT_DIR}/vpn-client.key
tls-auth ${OVPN_CLIENT_DIR}/ta.key 1
cipher AES-256-GCM
auth   SHA256
compress lz4-v2
tun-mtu 1200
mssfix 1100
verb 3
EOF

  cat > "${OVPN_CLIENT_DIR}/client-tcp.conf" <<EOF
client
dev tun
proto tcp
remote ${VM1_IP} 1194
resolv-retry infinite
nobind
persist-key
persist-tun
ca   ${OVPN_CLIENT_DIR}/ca.crt
cert ${OVPN_CLIENT_DIR}/vpn-client.crt
key  ${OVPN_CLIENT_DIR}/vpn-client.key
tls-auth ${OVPN_CLIENT_DIR}/ta.key 1
cipher AES-256-GCM
auth   SHA256
compress lz4-v2
tun-mtu 1200
mssfix 1100
verb 3
EOF

  info "OpenVPN client configured ✓"
}

# ── 4. strongSwan client ──────────────────────────────────────────────────────
setup_ipsec_client() {
  info "Setting up strongSwan IPSec client…"

  IPSEC_USER="${IPSEC_USER:-vpnbench}"
  IPSEC_PASS="${IPSEC_PASS:-changeme_strong_password}"

  cat > /etc/ipsec.conf <<IPSEC_CONF
config setup
    charondebug="ike 1, knl 1, cfg 0"

conn vpn-bench
    auto=add
    keyexchange=ikev2
    left=%any
    leftauth=eap-mschapv2
    leftsourceip=%config
    right=${VM1_IP}
    rightid=${VM1_IP}
    rightsubnet=0.0.0.0/0
    rightauth=pubkey
    eap_identity=${IPSEC_USER}
    aaa_identity=%any
IPSEC_CONF

  echo "${VM1_IP} : EAP \"${IPSEC_PASS}\"" >> /etc/ipsec.secrets
  echo "${IPSEC_USER} : EAP \"${IPSEC_PASS}\"" >> /etc/ipsec.secrets

  info "strongSwan client configured ✓"
}

# ── 5. Verify tc netem is available ──────────────────────────────────────────
verify_netem() {
  info "Verifying tc netem…"
  if ! tc qdisc show dev "${IFACE}" &>/dev/null; then
    error "tc command failed on interface ${IFACE}. Check IFACE env variable."
  fi
  # Quick smoke test
  tc qdisc replace dev "${IFACE}" root netem delay 10ms loss 0%
  tc qdisc del dev "${IFACE}" root
  info "tc netem working ✓"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  require_root
  configure_sudoers
  install_packages
  setup_wireguard_client
  setup_openvpn_client
  setup_ipsec_client
  verify_netem

  info "==================================================="
  info "VM2 setup complete!"
  info "Next: run generate_vpn_configs.sh to exchange keys."
  info "==================================================="
}

main "$@"
