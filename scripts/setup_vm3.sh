#!/usr/bin/env bash
# =============================================================================
# setup_vm3.sh — VPN Benchmark Suite: VM3 (Realtime Network Test Node) Setup
# =============================================================================
# VM3 purpose:
#   • Apply dynamic network conditions (tc netem)
#   • Generate test traffic (iperf3, hping3, ping)
#   • Provide diagnostics (mtr, tcpdump, netcat)
#   • Serve as remote worker controlled over SSH by backend
#
# Usage:
#   chmod +x setup_vm3.sh
#   sudo bash setup_vm3.sh
#
# Optional env vars:
#   IFACE=eth0
# =============================================================================

set -euo pipefail

IFACE="${IFACE:-tailscale0}"

info()  { echo -e "\033[0;32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

require_root() {
  [[ "$EUID" -eq 0 ]] || error "Please run as root (sudo bash $0)"
}

configure_sudoers() {
  info "Configuring passwordless sudo for SSH automation..."
  SSH_USER="${SUDO_USER:-$USER}"
  echo "${SSH_USER} ALL=(ALL) NOPASSWD: ALL" | tee /etc/sudoers.d/vpn-bench > /dev/null
  chmod 440 /etc/sudoers.d/vpn-bench
  info "Sudoers configured for ${SSH_USER}."
}

install_packages() {
  info "Updating package lists..."
  apt-get update -qq

  info "Installing realtime network test toolchain..."
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    iperf3 \
    hping3 \
    iproute2 \
    iputils-ping \
    net-tools \
    curl \
    jq \
    mtr-tiny \
    traceroute \
    tcpdump \
    netcat-openbsd \
    dnsutils \
    procps \
    sysstat
}

verify_interface() {
  info "Verifying network interface ${IFACE}..."
  ip link show "${IFACE}" >/dev/null 2>&1 || error "Interface ${IFACE} not found."
}

verify_netem() {
  info "Verifying tc netem on ${IFACE}..."
  tc qdisc show dev "${IFACE}" >/dev/null 2>&1 || error "tc qdisc cannot access ${IFACE}"
  tc qdisc replace dev "${IFACE}" root netem delay 10ms loss 0%
  tc qdisc del dev "${IFACE}" root || true
  info "tc netem working."
}

prepare_dirs() {
  info "Preparing runtime directories..."
  install -d -m 755 /var/log/vpn-bench
  install -d -m 755 /opt/vpn-bench
}

main() {
  require_root
  configure_sudoers
  install_packages
  verify_interface
  verify_netem
  prepare_dirs

  info "==================================================="
  info "VM3 setup complete."
  info "Ready for realtime network test orchestration."
  info "==================================================="
}

main "$@"
