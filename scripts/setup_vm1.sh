#!/usr/bin/env bash
# =============================================================================
# setup_vm1.sh — VPN Benchmark Suite: VM1 (Server) Setup
# =============================================================================
# Run once on VM1 (Ubuntu 22.04 / 24.04) to install and configure:
#   • WireGuard
#   • OpenVPN (UDP + TCP servers)
#   • strongSwan (IPSec/IKEv2)
#   • iperf3
#   • vmstat (sysstat)
#
# Usage:
#   chmod +x setup_vm1.sh
#   sudo bash setup_vm1.sh
#
# All values are read from environment variables so you can override defaults
# without editing this script.
# =============================================================================

set -euo pipefail

# ── Configurable via environment variables ────────────────────────────────────
VM1_IP="${VM1_IP:-192.168.80.141}"
VM2_IP="${VM2_IP:-192.168.80.145}"
IFACE="${IFACE:-ens33}"

WG_SERVER_IP="${WG_SERVER_IP:-10.200.0.1/24}"
WG_CLIENT_IP="${WG_CLIENT_IP:-10.200.0.2/32}"
WG_PORT="${WG_PORT:-51820}"

OVPN_UDP_PORT="${OVPN_UDP_PORT:-1194}"
OVPN_TCP_PORT="${OVPN_TCP_PORT:-1194}"

IPSEC_SERVER_IP="${IPSEC_SERVER_IP:-10.10.0.1}"
IPSEC_CLIENT_IP="${IPSEC_CLIENT_IP:-10.10.0.2}"
IPSEC_IKE="${IPSEC_IKE:-aes128-sha256-modp2048}"
IPSEC_ESP="${IPSEC_ESP:-aes128gcm16-modp2048}"

KEY_DIR="${KEY_DIR:-/etc/vpn-bench/keys}"
OVPN_SERVER_DIR="${OVPN_SERVER_DIR:-/etc/openvpn/server}"
OVPN_CLIENT_DIR="${OVPN_CLIENT_DIR:-/etc/openvpn/client}"

# ── Helpers ───────────────────────────────────────────────────────────────────
info()  { echo -e "\033[0;32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
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

# ── 1. System update + package install ───────────────────────────────────────
install_packages() {
  info "Updating package lists…"
  apt-get update -qq

  info "Installing packages…"
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    wireguard               \
    openvpn                 \
    easy-rsa                \
    strongswan              \
    strongswan-pki          \
    libcharon-extra-plugins \
    iperf3                  \
    sysstat                 \
    iproute2                \
    net-tools               \
    curl                    \
    ufw
}

# ── 2. Enable IP forwarding ───────────────────────────────────────────────────
enable_ip_forwarding() {
  info "Enabling IP forwarding…"
  sysctl -w net.ipv4.ip_forward=1
  grep -q "^net.ipv4.ip_forward=1" /etc/sysctl.conf \
    || echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
}

# ── 3. WireGuard server ───────────────────────────────────────────────────────
setup_wireguard() {
  info "Setting up WireGuard server…"
  mkdir -p /etc/wireguard
  chmod 700 /etc/wireguard

  # Generate server keys
  wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
  chmod 600 /etc/wireguard/server_private.key

  SERVER_PRIVKEY=$(cat /etc/wireguard/server_private.key)

  # Placeholder client pubkey — replaced by generate_vpn_configs.sh
  CLIENT_PUBKEY="${CLIENT_PUBKEY:-PLACEHOLDER_CLIENT_PUBKEY}"

  cat > /etc/wireguard/wg0.conf <<WG_CONF
[Interface]
Address = ${WG_SERVER_IP}
ListenPort = ${WG_PORT}
PrivateKey = ${SERVER_PRIVKEY}
PostUp   = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ${IFACE} -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ${IFACE} -j MASQUERADE

[Peer]
PublicKey  = ${CLIENT_PUBKEY}
AllowedIPs = ${WG_CLIENT_IP}
WG_CONF

  chmod 600 /etc/wireguard/wg0.conf
  systemctl enable wg-quick@wg0
  info "WireGuard configured ✓"
}

# ── 4. OpenVPN PKI + server configs ──────────────────────────────────────────
setup_openvpn() {
  info "Setting up OpenVPN PKI…"
  mkdir -p "${KEY_DIR}"
  mkdir -p "${OVPN_SERVER_DIR}" "${OVPN_CLIENT_DIR}"

  EASYRSA_DIR=/usr/share/easy-rsa
  PKIROOT="${KEY_DIR}/easy-rsa-local/pki"

  cd "${KEY_DIR}"
  cp -r "${EASYRSA_DIR}" ./easy-rsa-local
  cd easy-rsa-local

  ./easyrsa init-pki
  echo "VPN-Bench-CA" | ./easyrsa build-ca nopass
  ./easyrsa build-server-full vpn-server nopass
  ./easyrsa build-client-full vpn-client nopass
  ./easyrsa gen-dh
  openvpn --genkey secret "${PKIROOT}/ta.key"

  # Copy to OpenVPN dirs
  cp "${PKIROOT}/ca.crt"                 "${OVPN_SERVER_DIR}/"
  cp "${PKIROOT}/issued/vpn-server.crt"  "${OVPN_SERVER_DIR}/"
  cp "${PKIROOT}/private/vpn-server.key" "${OVPN_SERVER_DIR}/"
  cp "${PKIROOT}/dh.pem"                 "${OVPN_SERVER_DIR}/"
  cp "${PKIROOT}/ta.key"                 "${OVPN_SERVER_DIR}/"
  cp "${PKIROOT}/ca.crt"                 "${OVPN_CLIENT_DIR}/"
  cp "${PKIROOT}/issued/vpn-client.crt"  "${OVPN_CLIENT_DIR}/"
  cp "${PKIROOT}/private/vpn-client.key" "${OVPN_CLIENT_DIR}/"
  cp "${PKIROOT}/ta.key"                 "${OVPN_CLIENT_DIR}/"

  # UDP server config
  cat > "${OVPN_SERVER_DIR}/server-udp.conf" <<EOF
port ${OVPN_UDP_PORT}
proto udp
dev tun
ca   ${OVPN_SERVER_DIR}/ca.crt
cert ${OVPN_SERVER_DIR}/vpn-server.crt
key  ${OVPN_SERVER_DIR}/vpn-server.key
dh   ${OVPN_SERVER_DIR}/dh.pem
tls-auth ${OVPN_SERVER_DIR}/ta.key 0
server 10.8.0.0 255.255.255.0
cipher AES-256-GCM
auth   SHA256
keepalive 10 120
compress lz4-v2
push "compress lz4-v2"
user nobody
group nogroup
persist-key
persist-tun
status /tmp/openvpn-udp-status.log
verb 3
EOF

  # TCP server config
  cat > "${OVPN_SERVER_DIR}/server-tcp.conf" <<EOF
port ${OVPN_TCP_PORT}
proto tcp
dev tun1
ca   ${OVPN_SERVER_DIR}/ca.crt
cert ${OVPN_SERVER_DIR}/vpn-server.crt
key  ${OVPN_SERVER_DIR}/vpn-server.key
dh   ${OVPN_SERVER_DIR}/dh.pem
tls-auth ${OVPN_SERVER_DIR}/ta.key 0
server 10.9.0.0 255.255.255.0
cipher AES-256-GCM
auth   SHA256
keepalive 10 120
compress lz4-v2
push "compress lz4-v2"
user nobody
group nogroup
persist-key
persist-tun
status /tmp/openvpn-tcp-status.log
verb 3
EOF

  systemctl enable openvpn-server@server-udp
  systemctl enable openvpn-server@server-tcp
  info "OpenVPN configured ✓"
}

# ── 5. strongSwan (IPSec/IKEv2) ──────────────────────────────────────────────
setup_ipsec() {
  info "Setting up strongSwan IPSec…"

  IPSEC_DIR=/etc/ipsec.d
  mkdir -p "${IPSEC_DIR}/private" "${IPSEC_DIR}/certs" "${IPSEC_DIR}/cacerts"

  # Self-signed CA
  ipsec pki --gen --type rsa --size 4096 \
    --outform pem > "${IPSEC_DIR}/private/ca.key.pem"
  ipsec pki --self --ca --lifetime 3650 \
    --in "${IPSEC_DIR}/private/ca.key.pem" --type rsa \
    --dn "CN=VPN-Bench-CA" --outform pem \
    > "${IPSEC_DIR}/cacerts/ca.cert.pem"

  # Server cert
  ipsec pki --gen --type rsa --size 2048 \
    --outform pem > "${IPSEC_DIR}/private/server.key.pem"
  ipsec pki --pub --in "${IPSEC_DIR}/private/server.key.pem" --type rsa \
    | ipsec pki --issue --lifetime 1825 \
      --cacert "${IPSEC_DIR}/cacerts/ca.cert.pem" \
      --cakey  "${IPSEC_DIR}/private/ca.key.pem" \
      --dn "CN=${VM1_IP}" --san "${VM1_IP}" \
      --flag serverAuth --flag ikeIntermediate \
      --outform pem > "${IPSEC_DIR}/certs/server.cert.pem"

  cat > /etc/ipsec.conf <<IPSEC_CONF
config setup
    charondebug="ike 1, knl 1, cfg 0"

conn vpn-bench
    auto=add
    compress=no
    type=tunnel
    keyexchange=ikev2
    fragmentation=yes
    forceencaps=yes
    dpdaction=clear
    dpddelay=300s
    rekey=no
    left=%any
    leftid=${VM1_IP}
    leftcert=server.cert.pem
    leftsendcert=always
    leftsubnet=0.0.0.0/0
    right=%any
    rightid=%any
    rightauth=eap-mschapv2
    rightsourceip=${IPSEC_CLIENT_IP}/24
    rightdns=8.8.8.8
    rightsendcert=never
    eap_identity=%identity
    ike=${IPSEC_IKE}!
    esp=${IPSEC_ESP}!
IPSEC_CONF

  # PSK / EAP secret — change in production
  echo "${VM1_IP} : RSA server.key.pem" >> /etc/ipsec.secrets

  # Service name differs by distro/package variant.
  if systemctl list-unit-files | grep -q '^strongswan-starter\.service'; then
    systemctl enable strongswan-starter
    systemctl restart strongswan-starter
    info "strongSwan configured via strongswan-starter ✓"
  elif systemctl list-unit-files | grep -q '^strongswan\.service'; then
    systemctl enable strongswan
    systemctl restart strongswan
    info "strongSwan configured via strongswan ✓"
  elif systemctl list-unit-files | grep -q '^strongswan-swanctl\.service'; then
    systemctl enable strongswan-swanctl
    systemctl restart strongswan-swanctl
    info "strongSwan configured via strongswan-swanctl ✓"
  else
    warn "No strongSwan systemd unit found (starter/strongswan/swanctl)."
    warn "IPSec binaries are installed, but service enable/start was skipped."
  fi
}

# ── 6. UFW / firewall ─────────────────────────────────────────────────────────
configure_firewall() {
  info "Configuring UFW firewall…"
  ufw --force reset
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow ssh
  ufw allow "${WG_PORT}/udp"        comment "WireGuard"
  ufw allow "${OVPN_UDP_PORT}/udp"  comment "OpenVPN UDP"
  ufw allow "${OVPN_TCP_PORT}/tcp"  comment "OpenVPN TCP"
  ufw allow 500/udp  comment "IKEv2"
  ufw allow 4500/udp comment "IKEv2 NAT-T"
  ufw allow 5201     comment "iperf3"
  ufw --force enable
  info "Firewall configured ✓"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  require_root
  configure_sudoers
  install_packages
  enable_ip_forwarding
  setup_wireguard
  setup_openvpn
  setup_ipsec
  configure_firewall

  info "==================================================="
  info "VM1 setup complete!"
  info "Next: run generate_vpn_configs.sh to exchange keys."
  info "==================================================="
}

main "$@"
