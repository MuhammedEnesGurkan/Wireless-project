#!/usr/bin/env bash
# =============================================================================
# deploy_remote_setup.sh
# =============================================================================
# Host-side helper to deploy and run VM setup scripts on another Linux machine.
#
# Examples:
#   bash scripts/deploy_remote_setup.sh \
#     --role vm1 --host 100.70.73.68 --user wazuh --vm1-ip 100.70.73.68 --vm2-ip 100.101.234.82
#
#   bash scripts/deploy_remote_setup.sh \
#     --role vm2 --host 100.101.234.82 --user sshka --vm1-ip 100.70.73.68 --vm2-ip 100.101.234.82 --iface tailscale0
#
# Optional:
#   --key ~/.ssh/id_ed25519
#   --port 22
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

info()  { echo -e "\033[0;32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage:
  bash scripts/deploy_remote_setup.sh --role vm1|vm2 --host <ip_or_dns> --user <ssh_user> [options]

Required:
  --role      Target role: vm1 or vm2
  --host      Target machine IP/hostname
  --user      SSH username on target machine

Optional:
  --port      SSH port (default: 22)
  --key       SSH private key path (default: use SSH agent/default keys)
  --iface     Network interface passed to setup script (default: tailscale0)
  --vm1-ip    VM1 IP passed to setup script (default: 100.70.73.68)
  --vm2-ip    VM2 IP passed to setup script (default: 100.101.234.82)
  -h, --help  Show this help
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
    -h|--help) usage; exit 0 ;;
    *) error "Unknown argument: $1" ;;
  esac
done

[[ -n "${ROLE}" ]] || { usage; error "--role is required"; }
[[ -n "${HOST}" ]] || { usage; error "--host is required"; }
[[ -n "${USER_NAME}" ]] || { usage; error "--user is required"; }
[[ "${ROLE}" == "vm1" || "${ROLE}" == "vm2" ]] || error "--role must be vm1 or vm2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${ROLE}" == "vm1" ]]; then
  SETUP_SCRIPT="${PROJECT_ROOT}/scripts/setup_vm1.sh"
else
  SETUP_SCRIPT="${PROJECT_ROOT}/scripts/setup_vm2.sh"
fi
CHECK_SCRIPT="${PROJECT_ROOT}/scripts/check_setup.sh"

[[ -f "${SETUP_SCRIPT}" ]] || error "Setup script not found: ${SETUP_SCRIPT}"
[[ -f "${CHECK_SCRIPT}" ]] || error "Check script not found: ${CHECK_SCRIPT}"

SSH_OPTS=(-p "${PORT}" -o StrictHostKeyChecking=no)
SCP_OPTS=(-P "${PORT}" -o StrictHostKeyChecking=no)
if [[ -n "${KEY}" ]]; then
  [[ -f "${KEY}" ]] || error "SSH key not found: ${KEY}"
  SSH_OPTS+=(-i "${KEY}")
  SCP_OPTS+=(-i "${KEY}")
fi

REMOTE="${USER_NAME}@${HOST}"
REMOTE_SETUP="~/$(basename "${SETUP_SCRIPT}")"
REMOTE_CHECK="~/$(basename "${CHECK_SCRIPT}")"

info "Uploading scripts to ${REMOTE}..."
scp "${SCP_OPTS[@]}" "${SETUP_SCRIPT}" "${REMOTE}:${REMOTE_SETUP}"
scp "${SCP_OPTS[@]}" "${CHECK_SCRIPT}" "${REMOTE}:${REMOTE_CHECK}"

info "Normalizing script line endings on remote host..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" \
  "sed -i 's/\r$//' ${REMOTE_SETUP} ${REMOTE_CHECK}"

info "Running ${ROLE} setup on ${HOST}..."
ssh "${SSH_OPTS[@]}" "${REMOTE}" \
  "chmod +x ${REMOTE_SETUP} ${REMOTE_CHECK} && \
   sudo VM1_IP='${VM1_IP}' VM2_IP='${VM2_IP}' IFACE='${IFACE}' bash ${REMOTE_SETUP}"

info "Running post-setup checks on ${HOST}..."
if [[ "${ROLE}" == "vm1" ]]; then
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "sudo VM1_IP='${VM1_IP}' VM2_IP='${VM2_IP}' IFACE='${IFACE}' bash ${REMOTE_CHECK} --vm1"
else
  ssh "${SSH_OPTS[@]}" "${REMOTE}" \
    "sudo VM1_IP='${VM1_IP}' VM2_IP='${VM2_IP}' IFACE='${IFACE}' bash ${REMOTE_CHECK} --vm2"
fi

info "Done. ${ROLE} setup + verification completed on ${HOST}."
warn "If this host will participate in VPN tests, run key/config exchange from host machine:"
warn "  bash scripts/generate_vpn_configs.sh"
