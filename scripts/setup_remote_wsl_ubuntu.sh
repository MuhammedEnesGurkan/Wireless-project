#!/usr/bin/env bash
# =============================================================================
# setup_remote_wsl_ubuntu.sh
# =============================================================================
# Bootstrap a remote Ubuntu VM running on WSL in progressive stages:
#   1) Base OS update
#   2) Core tooling
#   3) Python runtime
#   4) Node.js runtime
#   5) SSH server setup
#   6) Optional Docker setup
#
# Usage:
#   chmod +x scripts/setup_remote_wsl_ubuntu.sh
#   sudo bash scripts/setup_remote_wsl_ubuntu.sh
#
# Optional env vars:
#   INSTALL_DOCKER=true|false   (default: true)
#   NODE_MAJOR=20               (default: 20)
# =============================================================================

set -euo pipefail

INSTALL_DOCKER="${INSTALL_DOCKER:-true}"
NODE_MAJOR="${NODE_MAJOR:-20}"

info() { echo -e "\033[0;32m[INFO]\033[0m  $*"; }
warn() { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

require_root() {
  [[ "$EUID" -eq 0 ]] || error "Run as root: sudo bash $0"
}

is_wsl() {
  grep -qi "microsoft\|wsl" /proc/version
}

has_systemd() {
  [[ -d /run/systemd/system ]]
}

restart_or_start_service() {
  local service_name="$1"
  if has_systemd; then
    systemctl enable "${service_name}" >/dev/null 2>&1 || true
    systemctl restart "${service_name}" >/dev/null 2>&1 || systemctl start "${service_name}" >/dev/null 2>&1 || true
    return 0
  fi

  if command -v service >/dev/null 2>&1; then
    service "${service_name}" restart >/dev/null 2>&1 || service "${service_name}" start >/dev/null 2>&1 || true
    return 0
  fi

  return 1
}

step_1_update_upgrade() {
  info "Step 1/6: Updating Ubuntu package index..."
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
}

step_2_install_core_tools() {
  info "Step 2/6: Installing core system tools..."
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    gnupg \
    lsb-release \
    apt-transport-https \
    software-properties-common \
    git \
    unzip \
    zip \
    jq \
    build-essential \
    net-tools \
    iproute2 \
    iputils-ping \
    openssl \
    tmux \
    htop
}

step_3_install_python() {
  info "Step 3/6: Installing Python runtime..."
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv

  python3 --version || true
  pip3 --version || true
}

step_4_install_node() {
  info "Step 4/6: Installing Node.js ${NODE_MAJOR}.x..."
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nodejs

  node --version || true
  npm --version || true
}

step_5_setup_ssh() {
  info "Step 5/6: Installing and configuring OpenSSH server..."
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openssh-server

  mkdir -p /var/run/sshd
  if ! restart_or_start_service ssh; then
    warn "Could not start ssh service automatically."
    warn "If running WSL without systemd, start manually with: sudo service ssh start"
  fi

  if grep -qE '^[#[:space:]]*PasswordAuthentication' /etc/ssh/sshd_config; then
    sed -i 's/^[#[:space:]]*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
  else
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config
  fi

  if grep -qE '^[#[:space:]]*PubkeyAuthentication' /etc/ssh/sshd_config; then
    sed -i 's/^[#[:space:]]*PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
  else
    echo "PubkeyAuthentication yes" >> /etc/ssh/sshd_config
  fi

  restart_or_start_service ssh || true
}

step_6_install_docker_optional() {
  if [[ "${INSTALL_DOCKER}" != "true" ]]; then
    info "Step 6/6: Docker installation skipped (INSTALL_DOCKER=${INSTALL_DOCKER})."
    return 0
  fi

  info "Step 6/6: Installing Docker Engine + Compose plugin..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update -y
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

  if ! restart_or_start_service docker; then
    warn "Could not start Docker service automatically."
    if is_wsl; then
      warn "In WSL, enable systemd in /etc/wsl.conf for service auto-start."
    fi
  fi
}

print_next_steps() {
  info "==================================================="
  info "Remote WSL Ubuntu bootstrap completed."
  info "Next:"
  info "  1) Add your SSH public key into ~/.ssh/authorized_keys"
  info "  2) Verify SSH from host: ssh <user>@<remote-ip>"
  info "  3) Run project VM role setup: scripts/setup_vm1.sh or scripts/setup_vm2.sh"
  info "==================================================="
}

main() {
  require_root
  step_1_update_upgrade
  step_2_install_core_tools
  step_3_install_python
  step_4_install_node
  step_5_setup_ssh
  step_6_install_docker_optional
  print_next_steps
}

main "$@"
