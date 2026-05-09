#!/usr/bin/env bash
# =============================================================================
# fix_ipsec_tailscale.sh
# =============================================================================
# Repairs the strongSwan IPSec/IKEv2 setup for the VPN Benchmark project when
# the VMs communicate over Tailscale.
#
# Run on VM1:
#   sudo bash fix_ipsec_tailscale.sh --vm1
#
# Then copy the generated CA to VM2:
#   scp /tmp/ca.cert.pem <vm2-user>@<vm2-tailscale-ip>:/tmp/ca.cert.pem
#
# Run on VM2:
#   sudo bash fix_ipsec_tailscale.sh --vm2
#
# Or run on VM3:
#   sudo bash fix_ipsec_tailscale.sh --vm3
#
# Optional environment overrides:
#   VM1_TS_IP=100.70.73.68
#   VM2_TS_IP=100.101.234.82
#   VM3_TS_IP=100.85.164.55
#   IPSEC_USER=vpnbench
#   IPSEC_PASS=changeme_strong_password
#   IPSEC_SERVER_IP=10.10.0.1
#   IPSEC_CLIENT_IP=10.10.0.2
#   TAILSCALE_IFACE=tailscale0
# =============================================================================

set -euo pipefail

ROLE="${1:-}"

VM1_TS_IP="${VM1_TS_IP:-100.70.73.68}"
VM2_TS_IP="${VM2_TS_IP:-100.101.234.82}"
VM3_TS_IP="${VM3_TS_IP:-100.85.164.55}"
IPSEC_USER="${IPSEC_USER:-vpnbench}"
IPSEC_PASS="${IPSEC_PASS:-changeme_strong_password}"
IPSEC_SERVER_IP="${IPSEC_SERVER_IP:-10.10.0.1}"
IPSEC_CLIENT_IP="${IPSEC_CLIENT_IP:-10.10.0.2}"
TAILSCALE_IFACE="${TAILSCALE_IFACE:-tailscale0}"
CONN_NAME="${CONN_NAME:-vpn-bench}"
IKE_PROPOSAL="${IKE_PROPOSAL:-aes128-sha256-modp2048}"
ESP_PROPOSAL="${ESP_PROPOSAL:-aes128gcm16-modp2048}"

info() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*"; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

require_root() {
  [[ "${EUID}" -eq 0 ]] || die "Run with sudo."
}

detect_service() {
  local svc
  for svc in strongswan-starter strongswan ipsec strongswan-swanctl; do
    if systemctl list-unit-files "${svc}.service" 2>/dev/null | grep -q "${svc}.service"; then
      echo "${svc}"
      return 0
    fi
    if systemctl status "${svc}.service" >/dev/null 2>&1; then
      echo "${svc}"
      return 0
    fi
  done
  return 1
}

install_packages() {
  info "Installing strongSwan/Tailscale IPSec packages..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    strongswan \
    strongswan-pki \
    libcharon-extra-plugins \
    libcharon-extauth-plugins \
    libstrongswan-standard-plugins \
    libstrongswan-extra-plugins \
    openssl \
    iproute2 \
    iputils-ping \
    iperf3
}

enable_plugins() {
  info "Enabling openssl and eap-mschapv2 plugins..."
  mkdir -p /etc/strongswan.d/charon

  cat > /etc/strongswan.conf <<'EOF'
charon {
    load_modular = yes

    plugins {
        include strongswan.d/charon/*.conf
    }
}

include strongswan.d/*.conf
EOF

  cat > /etc/strongswan.d/charon/openssl.conf <<'EOF'
openssl {
    load = yes
}
EOF

  cat > /etc/strongswan.d/charon/eap-mschapv2.conf <<'EOF'
eap-mschapv2 {
    load = yes
}
EOF
}

restart_ipsec() {
  local svc
  if svc="$(detect_service)"; then
    info "Restarting ${svc}..."
    systemctl enable "${svc}" >/dev/null 2>&1 || true
    systemctl restart "${svc}"
  else
    warn "No strongSwan systemd service found; falling back to ipsec restart."
    ipsec restart
  fi
  ipsec rereadsecrets 2>/dev/null || true
  ipsec reload 2>/dev/null || true
}

setup_vm1() {
  install_packages
  enable_plugins

  info "Creating ${IPSEC_SERVER_IP}/24 on dummy interface ipsec0..."
  ip link add ipsec0 type dummy 2>/dev/null || true
  ip addr replace "${IPSEC_SERVER_IP}/24" dev ipsec0
  ip link set ipsec0 up

  info "Enabling IPv4 forwarding..."
  echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-vpnbench.conf
  sysctl -p /etc/sysctl.d/99-vpnbench.conf >/dev/null

  info "Allowing IPSec and benchmark traffic on VM1..."
  iptables -I INPUT -s "${VM2_TS_IP}" -p udp --dport 500 -j ACCEPT 2>/dev/null || true
  iptables -I INPUT -s "${VM2_TS_IP}" -p udp --dport 4500 -j ACCEPT 2>/dev/null || true
  iptables -I INPUT -s "${VM3_TS_IP}" -p udp --dport 500 -j ACCEPT 2>/dev/null || true
  iptables -I INPUT -s "${VM3_TS_IP}" -p udp --dport 4500 -j ACCEPT 2>/dev/null || true
  iptables -I INPUT -s 10.10.0.0/24 -p icmp -j ACCEPT 2>/dev/null || true
  iptables -I INPUT -s 10.10.0.0/24 -p tcp --dport 5201 -j ACCEPT 2>/dev/null || true

  info "Ensuring CA exists..."
  mkdir -p /etc/ipsec.d/private /etc/ipsec.d/certs /etc/ipsec.d/cacerts
  if [[ ! -f /etc/ipsec.d/private/ca.key.pem || ! -f /etc/ipsec.d/cacerts/ca.cert.pem ]]; then
    ipsec pki --gen --type rsa --size 4096 --outform pem > /etc/ipsec.d/private/ca.key.pem
    ipsec pki --self --ca --lifetime 3650 \
      --in /etc/ipsec.d/private/ca.key.pem --type rsa \
      --dn "CN=VPN-Bench-CA" --outform pem \
      > /etc/ipsec.d/cacerts/ca.cert.pem
  fi

  info "Regenerating VM1 server certificate for Tailscale IP ${VM1_TS_IP}..."
  mv /etc/ipsec.d/private/server.key.pem "/etc/ipsec.d/private/server.key.pem.bak.$(date +%s)" 2>/dev/null || true
  mv /etc/ipsec.d/certs/server.cert.pem "/etc/ipsec.d/certs/server.cert.pem.bak.$(date +%s)" 2>/dev/null || true

  ipsec pki --gen --type rsa --size 2048 --outform pem > /etc/ipsec.d/private/server.key.pem
  ipsec pki --pub --in /etc/ipsec.d/private/server.key.pem --type rsa \
    | ipsec pki --issue --lifetime 1825 \
      --cacert /etc/ipsec.d/cacerts/ca.cert.pem \
      --cakey /etc/ipsec.d/private/ca.key.pem \
      --dn "CN=${VM1_TS_IP}" \
      --san "${VM1_TS_IP}" \
      --flag serverAuth \
      --flag ikeIntermediate \
      --outform pem \
    > /etc/ipsec.d/certs/server.cert.pem
  chmod 600 /etc/ipsec.d/private/*.key.pem

  info "Writing VM1 /etc/ipsec.conf..."
  cat > /etc/ipsec.conf <<EOF
config setup
    charondebug="ike 2, knl 1, cfg 2"

conn ${CONN_NAME}
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
    leftid=${VM1_TS_IP}
    leftauth=pubkey
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
    ike=${IKE_PROPOSAL}!
    esp=${ESP_PROPOSAL}!
EOF

  info "Writing VM1 /etc/ipsec.secrets..."
  cat > /etc/ipsec.secrets <<EOF
${VM1_TS_IP} : RSA server.key.pem
${IPSEC_USER} : EAP "${IPSEC_PASS}"
EOF
  chmod 600 /etc/ipsec.secrets

  cp /etc/ipsec.d/cacerts/ca.cert.pem /tmp/ca.cert.pem
  chmod 644 /tmp/ca.cert.pem

  restart_ipsec

  info "VM1 done. Copy /tmp/ca.cert.pem to the client VM before running --vm2 or --vm3."
  info "VM2 example: scp /tmp/ca.cert.pem wazuhagent2@${VM2_TS_IP}:/tmp/ca.cert.pem"
  info "VM3 example: scp /tmp/ca.cert.pem agurk@${VM3_TS_IP}:/tmp/ca.cert.pem"
  ipsec pki --print --in /etc/ipsec.d/certs/server.cert.pem | grep -E 'subject|altNames' || true
  ipsec statusall | grep 'loaded plugins' || true
}

setup_client() {
  local role_label="$1"
  install_packages
  enable_plugins

  info "Installing CA certificate if /tmp/ca.cert.pem exists..."
  mkdir -p /etc/ipsec.d/cacerts
  if [[ -f /tmp/ca.cert.pem ]]; then
    mv /tmp/ca.cert.pem /etc/ipsec.d/cacerts/ca.cert.pem
    chmod 644 /etc/ipsec.d/cacerts/ca.cert.pem
  elif [[ ! -f /etc/ipsec.d/cacerts/ca.cert.pem ]]; then
    die "Missing CA cert. Copy VM1:/tmp/ca.cert.pem to this client VM as /tmp/ca.cert.pem and rerun."
  else
    warn "Using existing /etc/ipsec.d/cacerts/ca.cert.pem."
  fi

  info "Writing ${role_label} /etc/ipsec.conf..."
  cat > /etc/ipsec.conf <<EOF
config setup
    charondebug="ike 2, knl 1, cfg 2"

conn ${CONN_NAME}
    auto=add
    keyexchange=ikev2
    type=tunnel
    fragmentation=yes
    forceencaps=yes
    rekey=no
    left=%any
    leftid=${IPSEC_USER}
    leftauth=eap-mschapv2
    leftsourceip=%config
    right=${VM1_TS_IP}
    rightid=${VM1_TS_IP}
    rightsubnet=0.0.0.0/0
    rightauth=pubkey
    eap_identity=${IPSEC_USER}
    aaa_identity=%any
    ike=${IKE_PROPOSAL}!
    esp=${ESP_PROPOSAL}!
EOF

  info "Writing ${role_label} /etc/ipsec.secrets..."
  cat > /etc/ipsec.secrets <<EOF
${IPSEC_USER} : EAP "${IPSEC_PASS}"
EOF
  chmod 600 /etc/ipsec.secrets

  info "Adding helper to repair the route after ipsec up..."
  cat > /usr/local/sbin/vpnbench-ipsec-route <<EOF
#!/usr/bin/env bash
set -euo pipefail
ip route replace ${IPSEC_SERVER_IP}/32 dev ${TAILSCALE_IFACE} src ${IPSEC_CLIENT_IP}
EOF
  chmod 755 /usr/local/sbin/vpnbench-ipsec-route

  restart_ipsec

  info "${role_label} done. Testing connection..."
  ipsec down "${CONN_NAME}" 2>/dev/null || true
  ipsec up "${CONN_NAME}"
  /usr/local/sbin/vpnbench-ipsec-route
  ping -c 3 -W 3 "${IPSEC_SERVER_IP}"
}

setup_vm2() {
  setup_client "VM2"
}

setup_vm3() {
  setup_client "VM3"
}

usage() {
  cat <<EOF
Usage:
  sudo bash $0 --vm1
  sudo bash $0 --vm2
  sudo bash $0 --vm3

Environment overrides:
  VM1_TS_IP=${VM1_TS_IP}
  VM2_TS_IP=${VM2_TS_IP}
  VM3_TS_IP=${VM3_TS_IP}
  IPSEC_USER=${IPSEC_USER}
  IPSEC_PASS=${IPSEC_PASS}
  IPSEC_SERVER_IP=${IPSEC_SERVER_IP}
  IPSEC_CLIENT_IP=${IPSEC_CLIENT_IP}
  TAILSCALE_IFACE=${TAILSCALE_IFACE}
EOF
}

main() {
  require_root
  case "${ROLE}" in
    --vm1) setup_vm1 ;;
    --vm2) setup_vm2 ;;
    --vm3) setup_vm3 ;;
    *) usage; exit 1 ;;
  esac
}

main "$@"
