/**
 * Zustand global store — four slices:
 *   testSlice     → current test state
 *   metricsSlice  → live metric streams
 *   resultsSlice  → final results + recommendation
 *   uiSlice       → theme + layout state
 */

import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import type {
  TestPhase,
  VpnProtocol,
  NetworkCondition,
  LatencyDataPoint,
  ThroughputDataPoint,
  WsCpuMessage,
  WsResultFinal,
  PhaseLogEntry,
  SummaryRow,
  PresetsMap,
} from "@/types";
import { generateId } from "@/lib/utils";

// ── Slice Interfaces ───────────────────────────────────────────────────────────

interface TestSlice {
  running: boolean;
  phase: TestPhase;
  progress: number;
  progressLabel: string;
  currentRunId: number;
  nextRunId: number;
  selectedProtocol: VpnProtocol;
  selectedCondition: NetworkCondition;
  wsConnected: boolean;
  setRunning: (v: boolean) => void;
  setPhase: (phase: TestPhase) => void;
  setProgress: (percent: number, label: string) => void;
  setSelectedProtocol: (p: VpnProtocol) => void;
  setSelectedCondition: (c: NetworkCondition) => void;
  setWsConnected: (v: boolean) => void;
  beginRun: () => void;
}

interface MetricsSlice {
  latencyPoints: LatencyDataPoint[];
  throughputPoints: ThroughputDataPoint[];
  cpuSamples: WsCpuMessage[];
  addLatency: (protocol: string, timestamp: number, value_ms: number) => void;
  addThroughput: (
    protocol: string,
    timestamp: number,
    upload: number,
    download: number
  ) => void;
  addCpu: (sample: WsCpuMessage) => void;
  clearMetrics: () => void;
}

interface ResultsSlice {
  results: WsResultFinal[];
  summaryRows: SummaryRow[];
  recommendation: WsResultFinal | null;
  addResult: (result: WsResultFinal) => void;
  clearResults: () => void;
}

interface UiSlice {
  darkMode: boolean;
  sidebarOpen: boolean;
  activeTab: "latency" | "throughput";
  phaseLog: PhaseLogEntry[];
  presets: PresetsMap | null;
  toggleDarkMode: () => void;
  setSidebarOpen: (v: boolean) => void;
  setActiveTab: (tab: "latency" | "throughput") => void;
  appendLog: (entry: Omit<PhaseLogEntry, "id" | "timestamp">) => void;
  clearLog: () => void;
  setPresets: (presets: PresetsMap) => void;
}

// ── Combined store type ────────────────────────────────────────────────────────

type Store = TestSlice & MetricsSlice & ResultsSlice & UiSlice;

// ── MAX data points kept in memory ────────────────────────────────────────────
const MAX_LATENCY_POINTS = 120;
const MAX_THROUGHPUT_POINTS = 60;
const MAX_CPU_SAMPLES = 60;

// ── Store implementation ───────────────────────────────────────────────────────

export const useStore = create<Store>()(
  subscribeWithSelector((set, get) => ({
    // ── testSlice ──────────────────────────────────────────────────────────────
    running: false,
    phase: "idle",
    progress: 0,
    progressLabel: "",
    currentRunId: 0,
    nextRunId: 1,
    selectedProtocol: "wireguard",
    selectedCondition: "home_network",
    wsConnected: false,

    setRunning: (v) => set({ running: v }),
    setPhase: (phase) => set({ phase }),
    setProgress: (percent, label) => set({ progress: percent, progressLabel: label }),
    setSelectedProtocol: (selectedProtocol) => set({ selectedProtocol }),
    setSelectedCondition: (selectedCondition) => set({ selectedCondition }),
    setWsConnected: (wsConnected) => set({ wsConnected }),
    beginRun: () =>
      set((state) => ({
        currentRunId: state.nextRunId,
        nextRunId: state.nextRunId + 1,
      })),

    // ── metricsSlice ───────────────────────────────────────────────────────────
    latencyPoints: [],
    throughputPoints: [],
    cpuSamples: [],

    addLatency: (protocol, timestamp, value_ms) =>
      set((state) => {
        const points = [...state.latencyPoints];
        const existing = points.find((p) => p.timestamp === timestamp);
        if (existing) {
          existing[protocol] = value_ms;
        } else {
          const newPoint: LatencyDataPoint = { timestamp, [protocol]: value_ms };
          points.push(newPoint);
        }
        const sliced =
          points.length > MAX_LATENCY_POINTS
            ? points.slice(-MAX_LATENCY_POINTS)
            : points;
        return { latencyPoints: sliced };
      }),

    addThroughput: (protocol, timestamp, upload, download) =>
      set((state) => {
        const points = [
          ...state.throughputPoints,
          { timestamp, upload, download, protocol },
        ];
        const sliced =
          points.length > MAX_THROUGHPUT_POINTS
            ? points.slice(-MAX_THROUGHPUT_POINTS)
            : points;
        return { throughputPoints: sliced };
      }),

    addCpu: (sample) =>
      set((state) => {
        const samples = [...state.cpuSamples, sample];
        return {
          cpuSamples:
            samples.length > MAX_CPU_SAMPLES
              ? samples.slice(-MAX_CPU_SAMPLES)
              : samples,
        };
      }),

    clearMetrics: () =>
      set({ latencyPoints: [], throughputPoints: [], cpuSamples: [] }),

    // ── resultsSlice ───────────────────────────────────────────────────────────
    results: [],
    summaryRows: [],
    recommendation: null,

    addResult: (result) =>
      set((state) => {
        const results = [
          ...state.results.filter((r) => r.protocol !== result.protocol),
          result,
        ];
        const recommendation =
          results.find((r) => r.recommended) ?? null;
        const summaryRows: SummaryRow[] = [
          ...state.summaryRows,
          {
            run_id: state.currentRunId,
            recorded_at: Date.now(),
            protocol: result.protocol,
            condition: result.condition,
            avg_latency_ms: result.avg_latency_ms,
            max_latency_ms: result.max_latency_ms,
            avg_throughput_mbps: result.avg_throughput_mbps,
            avg_cpu_percent: result.avg_cpu_percent,
            score: result.score,
            recommended: result.recommended,
          },
        ];
        return { results, summaryRows, recommendation };
      }),

    clearResults: () =>
      set({ results: [], recommendation: null }),

    // ── uiSlice ────────────────────────────────────────────────────────────────
    darkMode: (() => {
      try {
        const s = localStorage.getItem("vpn-theme");
        return s === null ? true : s === "dark";
      } catch { return true; }
    })(),
    sidebarOpen: true,
    activeTab: "latency",
    phaseLog: [],
    presets: null,

    toggleDarkMode: () => set((state) => ({ darkMode: !state.darkMode })),
    setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
    setActiveTab: (activeTab) => set({ activeTab }),

    appendLog: (entry) =>
      set((state) => ({
        phaseLog: [
          ...state.phaseLog.slice(-199),
          {
            ...entry,
            id: generateId(),
            timestamp: Date.now(),
          },
        ],
      })),

    clearLog: () => set({ phaseLog: [] }),
    setPresets: (presets) => set({ presets }),
  }))
);

// ── Selector helpers ───────────────────────────────────────────────────────────

export const selectTestState = (s: Store) => ({
  running: s.running,
  phase: s.phase,
  progress: s.progress,
  progressLabel: s.progressLabel,
  selectedProtocol: s.selectedProtocol,
  selectedCondition: s.selectedCondition,
  wsConnected: s.wsConnected,
});

export const selectMetrics = (s: Store) => ({
  latencyPoints: s.latencyPoints,
  throughputPoints: s.throughputPoints,
  cpuSamples: s.cpuSamples,
});

export const selectResults = (s: Store) => ({
  results: s.results,
  summaryRows: s.summaryRows,
  recommendation: s.recommendation,
});

export const selectUi = (s: Store) => ({
  darkMode: s.darkMode,
  sidebarOpen: s.sidebarOpen,
  activeTab: s.activeTab,
  phaseLog: s.phaseLog,
  presets: s.presets,
});
