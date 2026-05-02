# 🛡️ Network Condition-Aware VPN Benchmark Suite

A production-quality web platform for benchmarking VPN protocols under realistic
network conditions — entirely browser-driven, no terminal required during the demo.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          HOST MACHINE                               │
│                                                                     │
│   ┌──────────────────────┐        ┌──────────────────────────────┐  │
│   │  Frontend (React 18) │◄──────►│  Backend (FastAPI)           │  │
│   │  Vite · Tailwind     │  HTTP  │  asyncssh · Pydantic v2      │  │
│   │  Zustand · Recharts  │◄──────►│  structlog · WebSocket       │  │
│   │  Framer Motion       │  WS    │  port 8000                   │  │
│   │  port 5173           │        └────────┬─────────────────────┘  │
│   └──────────────────────┘                 │  SSH (asyncssh pool)   │
│                                            │                        │
└────────────────────────────────────────────┼────────────────────────┘
                                             │
             ┌───────────────────────────────┤
             │                               │
             ▼                               ▼
  ┌──────────────────────┐       ┌───────────────────────┐
  │  VM1 — VPN Server    │◄─────►│  VM2 — VPN Client     │
  │  192.168.56.10       │  VPN  │  192.168.56.11        │
  │                      │tunnel │                       │
  │  • WireGuard         │       │  • wg-quick client    │
  │  • OpenVPN UDP/TCP   │       │  • openvpn client     │
  │  • strongSwan IPSec  │       │  • ipsec client       │
  │  • iperf3 server     │       │  • iperf3 client      │
  │  • vmstat            │       │  • ping, hping3       │
  └──────────────────────┘       │  • tc netem           │
                                 └───────────────────────┘
```

**Data flow during a test:**

```
Browser → POST /api/test/start
       ← 202 Accepted

Backend SSH→VM2: tc qdisc replace (netem)
Backend SSH→VM1: systemctl start <vpn>
Backend SSH→VM2: wg-quick up / openvpn / ipsec up
Backend SSH→VM2: ping -i 0.5 -c 120 <vpn_ip>
  each ping line → WS latency message → Browser chart
Backend SSH→VM1: iperf3 -s; SSH→VM2: iperf3 -c -J
  result → WS throughput message → Browser chart
Backend SSH→VM1: vmstat 1 3
  result → WS cpu message → Browser
Score computed → WS result_final → Recommendation banner
Cleanup: tunnel down, netem reset
```

---

## Prerequisites

| Component        | Requirement                          |
|------------------|--------------------------------------|
| Host OS          | Linux / macOS / Windows (WSL2)       |
| Python           | 3.11+                                |
| Node.js          | 18+                                  |
| VM1 / VM2        | Ubuntu 22.04 or 24.04                |
| SSH access       | Key-based auth from host → both VMs  |
| Host → VMs       | Network reachable (VirtualBox/VMware)|

---

## Quick Start

### 1 — Clone & configure

```bash
git clone <repo-url> vpn-benchmark
cd vpn-benchmark

# Copy and edit the env file
cp .env.example .env
# Edit .env: set VM1_HOST, VM2_HOST, SSH_KEY_PATH, etc.

# Review config.yaml — all IPs, ports, test params live here
nano config.yaml
```

### 2 — Set up the VMs

Run these **on each respective VM** (requires sudo):

```bash
# On VM1
scp scripts/setup_vm1.sh ubuntu@192.168.56.10:~
ssh ubuntu@192.168.56.10 'sudo bash ~/setup_vm1.sh'

# On VM2
scp scripts/setup_vm2.sh ubuntu@192.168.56.11:~
ssh ubuntu@192.168.56.11 'sudo bash ~/setup_vm2.sh'
```

### 3 — Exchange VPN keys

Run **from the host**:

```bash
chmod +x scripts/generate_vpn_configs.sh
bash scripts/generate_vpn_configs.sh
```

This exchanges WireGuard public keys, distributes OpenVPN certificates,
and copies the IPSec CA cert — finishing with a smoke test ping.

### 4 — Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run from project root so config.yaml resolves correctly
cd ..
python -m backend.main
# → Listening on http://0.0.0.0:8000
```

### 5 — Start the frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### 6 — Run a benchmark

1. Open **http://localhost:5173**
2. Select a **Network Condition** (e.g. ✈️ Airplane WiFi)
3. Select a **Protocol** (e.g. WireGuard) or **All Protocols**
4. Click **▶ Start Test**
5. Watch live latency + throughput graphs stream in
6. See the recommendation banner once tests complete

---

## Configuration Reference (`config.yaml`)

```yaml
infrastructure:
  vm1:
    host: "192.168.56.10"     # VM1 IP — VPN server
    port: 22
    user: "ubuntu"
    ssh_key_path: "~/.ssh/vpn_bench_key"
    vpn_server_ip: "10.8.0.1"
    iperf3_port: 5201

  vm2:
    host: "192.168.56.11"     # VM2 IP — client + test engine
    ...
    network_interface: "eth0"  # Interface for tc netem

network_conditions:
  airplane_wifi:
    delay_ms: 600
    jitter_ms: 200
    loss_percent: 5.0
    rate_mbit: 2
    hping3_flood: false        # true only for stress_dos

tests:
  latency:
    ping_count: 120            # 60 s of 0.5 s pings
  throughput:
    iperf3_duration_sec: 30

scoring:
  latency_weight:    0.4       # weight for 1/avg_latency
  throughput_weight: 0.4       # weight for avg_throughput
  cpu_weight:        0.2       # weight for 1/avg_cpu
  score_max:         100
```

All values can be overridden via `.env` — no code changes needed.

---

## WebSocket Message Reference

Connect to `ws://localhost:8000/ws/test` to receive:

| `type`          | Fields                                                          |
|-----------------|-----------------------------------------------------------------|
| `status`        | `phase`, `message`                                              |
| `latency`       | `protocol`, `timestamp`, `value_ms`                             |
| `throughput`    | `protocol`, `timestamp`, `upload_mbps`, `download_mbps`         |
| `cpu`           | `host`, `timestamp`, `usage_percent`                            |
| `progress`      | `percent`, `label`                                              |
| `result_final`  | `protocol`, `condition`, `avg_*`, `score`, `recommended`        |
| `error`         | `phase`, `message`, `retry`                                     |
| `heartbeat`     | *(keep-alive, sent every 15 s)*                                 |

---

## Network Condition Presets

| Key              | Label          | Delay    | Jitter | Loss  | Rate    |
|------------------|----------------|----------|--------|-------|---------|
| `home_network`   | 🏠 Home         | 10 ms    | —      | 0.1%  | 100Mbit |
| `airplane_wifi`  | ✈️ Airplane     | 600 ms   | ±200ms | 5%    | 2Mbit   |
| `industrial_iot` | 🏗️ Industrial   | 80 ms    | ±20ms  | 2%    | 10Mbit  |
| `mobile_4g`      | 📱 4G Mobile    | 80 ms    | ±30ms  | 1%    | 20Mbit  |
| `stress_dos`     | 🔥 Stress/DoS   | 200 ms   | —      | 10%   | 5Mbit   |

`stress_dos` additionally launches an **hping3 SYN flood** against VM1 for 30 s.

---

## Scoring Formula

```
score = normalize(
    (1/avg_latency_ms)  × 0.4 +
    avg_throughput_mbps × 0.4 +
    (1/avg_cpu_percent) × 0.2
) × 100
```

The protocol with the highest score in each test run is marked **recommended**.

---

## Project Structure

```
vpn-benchmark/
├── config.yaml                  # All configuration — no hardcoded values
├── .env.example                 # Environment variable template
│
├── backend/
│   ├── main.py                  # FastAPI app + startup/shutdown
│   ├── requirements.txt
│   ├── core/
│   │   ├── config.py            # Pydantic-validated config loader
│   │   └── logging.py           # structlog JSON logging
│   ├── models/
│   │   └── schemas.py           # All Pydantic v2 schemas
│   ├── routers/
│   │   └── tests.py             # HTTP endpoints + WebSocket handler
│   └── services/
│       ├── ssh_manager.py       # asyncssh connection pool
│       ├── netem_manager.py     # tc netem apply/reset
│       ├── vpn_manager.py       # VPN start/stop/verify
│       └── metrics_collector.py # ping, iperf3 -J, vmstat
│
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts       # Custom dark theme tokens
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── styles/globals.css   # CSS variables + Tailwind base
│       ├── types/index.ts       # Shared TypeScript types
│       ├── lib/utils.ts         # cn(), protocol meta, formatters
│       ├── store/index.ts       # Zustand store (4 slices)
│       ├── hooks/
│       │   └── useVpnWebSocket.ts   # WS client + auto-reconnect
│       ├── services/
│       │   └── api.ts           # HTTP API client
│       └── components/
│           ├── ui/              # shadcn/ui primitives
│           │   ├── button.tsx
│           │   ├── card.tsx
│           │   ├── badge.tsx
│           │   ├── select.tsx
│           │   ├── separator.tsx
│           │   ├── switch.tsx
│           │   ├── progress.tsx
│           │   ├── alert.tsx
│           │   ├── tooltip.tsx
│           │   └── table.tsx
│           ├── Sidebar.tsx          # Left sidebar shell
│           ├── ControlPanel.tsx     # Condition/protocol pickers + buttons
│           ├── StatusIndicator.tsx  # Animated phase dot + badge
│           ├── PhaseLog.tsx         # Scrollable log with Framer fade-in
│           ├── LatencyChart.tsx     # Recharts AreaChart
│           ├── ThroughputChart.tsx  # Recharts LineChart
│           ├── SummaryTable.tsx     # shadcn Table + score badges
│           └── RecommendationBanner.tsx  # Framer slide-in banner
│
└── scripts/
    ├── setup_vm1.sh             # VM1 server-side setup
    ├── setup_vm2.sh             # VM2 client-side setup
    └── generate_vpn_configs.sh  # Key exchange from host
```

---

## Troubleshooting

**Backend can't SSH to VMs**
- Verify `SSH_KEY_PATH` in `.env` points to the correct private key
- Test manually: `ssh -i ~/.ssh/vpn_bench_key ubuntu@192.168.56.10`
- Ensure the public key is in `~/.ssh/authorized_keys` on both VMs

**WireGuard tunnel fails verification**
- Check UDP port `51820` is allowed through VM1 firewall: `sudo ufw status`
- Confirm VM2 can reach VM1: `ping 192.168.56.10`
- Inspect WG status: `sudo wg show` on both VMs

**iperf3 times out**
- Ensure iperf3 port `5201` is open on VM1: `sudo ufw allow 5201`
- Check iperf3 server starts: `sudo iperf3 -s -p 5201`

**tc netem permission denied**
- The SSH user must have passwordless sudo for `tc`:
  ```
  echo 'ubuntu ALL=(ALL) NOPASSWD: /sbin/tc' | sudo tee /etc/sudoers.d/tc
  ```

**Frontend can't reach backend**
- Verify `VITE_API_BASE_URL` and `VITE_WS_URL` in `frontend/.env`
- Check CORS origins in `config.yaml` include `http://localhost:5173`

---

## License

MIT — see LICENSE file.
