#!/usr/bin/env bash
# =============================================================================
# deploy_remote_wsl_and_setup.sh
# =============================================================================
# Host-side helper for remote Ubuntu-on-WSL setup flow:
#   1) Upload and run setup_remote_wsl_ubuntu.sh
#   2) Upload and run setup_vm1.sh / setup_vm2.sh / setup_vm3.sh
#   3) Run check_setup.sh verification
#
# Usage:
#   bash scripts/deploy_remote_wsl_and_setup.sh \
#     --role vm1 --host 100.70.73.68 --user wazuh --vm1-ip 100.70.73.68 --vm2-ip 100.101.234.82
#
#   bash scripts/deploy_remote_wsl_and_setup.sh \
#     --role vm3 --host 100.85.164.55 --user agurk --iface tailscale0 --skip-bootstrap
#
# Optional:
#   --key ~/.ssh/id_ed25519
#   --port 22
#   --iface eth0
#   --install-docker true|false
#   --skip-bootstrap
# =============================================================================

set -euo pipefail

ROLE=""
HOST=""
USER_NAME=""
PORT="22"
KEY=""
IFACE="tailscale0"
VM1_IP="100.70.73.68"
VM2_IP="100.101.234.82"
INSTALL_DOCKER="true"
SKIP_BOOTSTRAP="false"

info()  { echo -e "\033[0;32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  bash scripts/deploy_remote_wsl_and_setup.sh --role vm1|vm2|vm3 --host <ip_or_dns> --user <ssh_user> [options]

Required:
  --role      Target role: vm1, vm2, or vm3
  --host      Target machine IP/hostname
  --user      SSH username on target machine

Optional:
  --port             SSH port (default: 22)
  --key              SSH private key path
  --iface            Network interface passed to role setup (default: tailscale0)
  --vm1-ip           VM1 IP passed to role setup
  --vm2-ip           VM2 IP passed to role setup
  --install-docker   true|false (bootstrap step)
  --skip-bootstrap   Skip setup_remote_wsl_ubuntu.sh step
  -h, --help         Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) ROLE="${2:-}"; shift 2 ;;
    --host) HOST="${2:-}"; shift 2 ;;
    --user) USER_NAME="${2:-}"; shift 2 ;;
    --port) PORT="${2:-}"; shift 2 ;;
    --key) KEY="${2:-}"; shift 2 ;;
    --iface) IFACE="${2:-}"; shift 2 ;;
    --vm1-ip) VM1_IP="${2:-}"; shift 2 ;;
    --vm2-ip) VM2_IP="${2:-}"; shift 2 ;;
    --install-docker) INSTALL_DOCKER="${2:-}"; shift 2 ;;
    --skip-bootstrap) SKIP_BOOTSTRAP="true"; shift 1 ;;
    -h|--help) usage; exit 0 ;;
    *) error "Unknown argument: $1" ;;
  esac
done

[[ -n "${ROLE}" ]] || { usage; error "--role is required"; }
[[ -n "${HOST}" ]] || { usage; error "--host is required"; }
[[ -n "${USER_NAME}" ]] || { usage; error "--user is required"; }
[[ "${ROLE}" == "vm1" || "${ROLE}" == "vm2" || "${ROLE}" == "vm3" ]] || error "--role must be vm1, vm2, or vm3"
[[ "${INSTALL_DOCKER}" == "true" || "${INSTALL_DOCKER}" == "false" ]] || error "--install-docker must be true or false"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BOOTSTRAP_SCRIPT="${PROJECT_ROOT}/scripts/setup_remote_wsl_ubuntu.sh"
CHECK_SCRIPT="${PROJECT_ROOT}/scripts/check_setup.sh"
if [[ "${ROLE}" == "vm1" ]]; then
  ROLE_SCRIPT="${PROJECT_ROOT}/scripts/setup_vm1.sh"
elif [[ "${ROLE}" == "vm2" ]]; then
  ROLE_SCRIPT="${PROJECT_ROOT}/scripts/setup_vm2.sh"
else
  ROLE_SCRIPT="${PROJECT_ROOT}/scripts/setup_vm3.sh"
fi

[[ -f "${BOOTSTRAP_SCRIPT}" ]] || error "Bootstrap script not found: ${BOOTSTRAP_SCRIPT}"
[[ -f "${ROLE_SCRIPT}" ]] || error "Role script not found: ${ROLE_SCRIPT}"
[[ -f "${CHECK_SCRIPT}" ]] || error "Check script not found: ${CHECK_SCRIPT}"

SSH_OPTS=(-p "${PORT}" -o StrictHostKeyChecking=no)
SCP_OPTS=(-P "${PORT}" -o StrictHostKeyChecking=no)
if [[ -n "${KEY}" ]]; then
  [[ -f "${KEY}" ]] || error "SSH key not found: ${KEY}"
  SSH_OPTS+=(-i "${KEY}")
  SCP_OPTS+=(-i "${KEY}")
fi

REMOTE="${USER_NAME}@${HOST}"
REMOTE_BOOTSTRAP="~/$(basename "${BOOTSTRAP_SCRIPT}")"
REMOTE_ROLE="~/$(basename "${ROLE_SCRIPT}")"
REMOTE_CHECK="~/$(basename "${CHECK_SCRIPT}")"

info "Uploading scripts to ${REMOTE}..."
if [[ "${SKIP_BOOTSTRAP}" != "true" ]]; then
  scp "${SCP_OPTS[@]}" "${BOOTSTRAP_SCRIPT}" "${REMOTE}:${REMOTE_BOOTSTRAP}"
fi
scp "${SCP_OPTS[@]}" "${ROLE_SCRIPT}" "${REMOTE}:${REMOTE_ROLE}"
scp "${SCP_OPTS[@]}" "${CHECK_SCRIPT}" "${REMOTE}:${REMOTE_CHECK}"

info "Normalizing script line endings on remote host..."
if [[ "${SKIP_BOOTSTRAP}" != "true" ]]; then
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "sed -i 's/\r$//' ${REMOTE_BOOTSTRAP} ${REMOTE_ROLE} ${REMOTE_CHECK}"
else
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "sed -i 's/\r$//' ${REMOTE_ROLE} ${REMOTE_CHECK}"
fi

if [[ "${SKIP_BOOTSTRAP}" != "true" ]]; then
  info "Running WSL Ubuntu bootstrap on ${HOST}..."
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "chmod +x ${REMOTE_BOOTSTRAP} && sudo INSTALL_DOCKER='${INSTALL_DOCKER}' bash ${REMOTE_BOOTSTRAP}"
else
  warn "Bootstrap step skipped (--skip-bootstrap)."
fi

info "Running ${ROLE} setup on ${HOST}..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" \
  "chmod +x ${REMOTE_ROLE} ${REMOTE_CHECK} && sudo VM1_IP='${VM1_IP}' VM2_IP='${VM2_IP}' IFACE='${IFACE}' bash ${REMOTE_ROLE}"

info "Running post-setup checks on ${HOST}..."
if [[ "${ROLE}" == "vm1" ]]; then
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "sudo VM1_IP='${VM1_IP}' VM2_IP='${VM2_IP}' IFACE='${IFACE}' bash ${REMOTE_CHECK} --vm1"
elif [[ "${ROLE}" == "vm2" ]]; then
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "sudo VM1_IP='${VM1_IP}' VM2_IP='${VM2_IP}' IFACE='${IFACE}' bash ${REMOTE_CHECK} --vm2"
else
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "sudo VM1_IP='${VM1_IP}' VM2_IP='${VM2_IP}' IFACE='${IFACE}' bash ${REMOTE_CHECK} --vm3"
fi

info "Done. Remote WSL bootstrap + ${ROLE} setup + checks completed on ${HOST}."
