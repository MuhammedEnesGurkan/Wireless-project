/**
 * SetupWizard — shown automatically on first load when VMs are not configured.
 * Also provides ConnectivityStatusCard for the sidebar showing live VM status.
 */
import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertTriangle, Wifi, WifiOff, CheckCircle2, XCircle,
  Loader2, RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, type ConnectivityResult } from "@/services/api";

// ── Types ──────────────────────────────────────────────────────────────────────

type VmStatus = "unknown" | "checking" | "ok" | "error";

interface VmStatusState {
  vm1: VmStatus; vm1Msg: string; vm1Latency: number | null;
  vm2: VmStatus; vm2Msg: string; vm2Latency: number | null;
  vm3: VmStatus; vm3Msg: string; vm3Latency: number | null;
  hasVm3: boolean;
}

const INITIAL_STATE: VmStatusState = {
  vm1: "unknown", vm1Msg: "Henüz test edilmedi", vm1Latency: null,
  vm2: "unknown", vm2Msg: "Henüz test edilmedi", vm2Latency: null,
  vm3: "unknown", vm3Msg: "", vm3Latency: null,
  hasVm3: false,
};

// ── Helpers ────────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<VmStatus, string> = {
  unknown:  "text-slate-500",
  checking: "text-yellow-400",
  ok:       "text-emerald-400",
  error:    "text-red-400",
};

const STATUS_BG: Record<VmStatus, string> = {
  unknown:  "bg-slate-500/10 border-slate-600/30",
  checking: "bg-yellow-400/10 border-yellow-400/20",
  ok:       "bg-emerald-400/10 border-emerald-400/20",
  error:    "bg-red-500/10 border-red-500/20",
};

function statusFromResult(r: ConnectivityResult | undefined): VmStatus {
  if (!r) return "error";
  return r.success ? "ok" : "error";
}

// ── VmStatusPill ───────────────────────────────────────────────────────────────

function VmStatusPill({
  label, status, message, latency,
}: {
  label: string;
  status: VmStatus;
  message: string;
  latency: number | null;
}) {
  return (
    <div className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-xs transition-colors ${STATUS_BG[status]}`}>
      <div className="mt-0.5 shrink-0">
        {status === "checking" && <Loader2 className={`h-3.5 w-3.5 animate-spin ${STATUS_COLOR.checking}`} />}
        {status === "ok"       && <CheckCircle2 className={`h-3.5 w-3.5 ${STATUS_COLOR.ok}`} />}
        {status === "error"    && <XCircle className={`h-3.5 w-3.5 ${STATUS_COLOR.error}`} />}
        {status === "unknown"  && <Wifi className={`h-3.5 w-3.5 ${STATUS_COLOR.unknown}`} />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className={`font-semibold ${STATUS_COLOR[status]}`}>{label}</span>
          {status === "ok" && latency !== null && (
            <span className="text-emerald-400/70 font-mono">{latency}ms</span>
          )}
        </div>
        <p className={`mt-0.5 break-all text-[10px] leading-relaxed ${
          status === "ok" ? "text-emerald-400/60" : "text-slate-400"
        }`}>
          {message}
        </p>
      </div>
    </div>
  );
}

// ── ConnectivityStatusCard — shown in the sidebar ──────────────────────────────

interface ConnectivityStatusCardProps {
  onOpenSettings: () => void;
}

export function ConnectivityStatusCard({ onOpenSettings }: ConnectivityStatusCardProps) {
  const [state, setState] = useState<VmStatusState>(INITIAL_STATE);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [checking, setChecking] = useState(false);

  const runCheck = useCallback(async () => {
    setChecking(true);
    setState((s) => ({
      ...s,
      vm1: "checking", vm1Msg: "Bağlanıyor…",
      vm2: "checking", vm2Msg: "Bağlanıyor…",
      vm3: s.hasVm3 ? "checking" : "unknown",
      vm3Msg: s.hasVm3 ? "Bağlanıyor…" : "",
    }));

    try {
      const results = await api.testConnectivity();
      const byVm = Object.fromEntries(results.map((r) => [r.vm, r]));
      const has3 = Boolean(byVm["vm3"]);

      setState({
        vm1: statusFromResult(byVm["vm1"]),
        vm1Msg: byVm["vm1"]?.message ?? "Yanıt yok",
        vm1Latency: byVm["vm1"]?.latency_ms ?? null,
        vm2: statusFromResult(byVm["vm2"]),
        vm2Msg: byVm["vm2"]?.message ?? "Yanıt yok",
        vm2Latency: byVm["vm2"]?.latency_ms ?? null,
        vm3: has3 ? statusFromResult(byVm["vm3"]) : "unknown",
        vm3Msg: byVm["vm3"]?.message ?? "",
        vm3Latency: byVm["vm3"]?.latency_ms ?? null,
        hasVm3: has3,
      });
      setLastChecked(new Date());
    } catch {
      setState((s) => ({
        ...s,
        vm1: "error", vm1Msg: "Backend'e ulaşılamıyor — çalışıyor mu?",
        vm2: "error", vm2Msg: "Backend'e ulaşılamıyor — çalışıyor mu?",
      }));
    } finally {
      setChecking(false);
    }
  }, []);

  const allOk =
    state.vm1 === "ok" &&
    state.vm2 === "ok" &&
    (!state.hasVm3 || state.vm3 === "ok");

  return (
    <div className="rounded-xl border border-vpn-border bg-black/20 p-3 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {allOk
            ? <Wifi className="h-3.5 w-3.5 text-emerald-400" />
            : <WifiOff className="h-3.5 w-3.5 text-slate-500" />
          }
          <span className="text-xs font-semibold text-slate-300">VM Bağlantıları</span>
        </div>
        <div className="flex items-center gap-2">
          {lastChecked && (
            <span className="text-[10px] text-slate-600">
              {lastChecked.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
          )}
          <button
            onClick={runCheck}
            disabled={checking}
            title="Tekrar test et"
            className="rounded p-0.5 text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`h-3 w-3 ${checking ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* VM status pills */}
      <div className="space-y-1.5">
        <VmStatusPill label="VM1 — VPN Server"   status={state.vm1} message={state.vm1Msg} latency={state.vm1Latency} />
        <VmStatusPill label="VM2 — VPN Client"   status={state.vm2} message={state.vm2Msg} latency={state.vm2Latency} />
        {state.hasVm3 && (
          <VmStatusPill label="VM3 — Benchmark"  status={state.vm3} message={state.vm3Msg} latency={state.vm3Latency} />
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 pt-0.5">
        <Button
          size="sm"
          variant="outline"
          className="flex-1 text-[11px] h-7 border-vpn-border text-slate-400 hover:text-slate-200 hover:bg-white/5 gap-1"
          onClick={runCheck}
          disabled={checking}
        >
          {checking
            ? <><Loader2 className="h-3 w-3 animate-spin" /> Test ediliyor…</>
            : <><RefreshCw className="h-3 w-3" /> Bağlantıyı Test Et</>
          }
        </Button>
        <Button
          size="sm"
          variant="outline"
          title="VM Ayarlarını Aç"
          className="text-[11px] h-7 px-2.5 border-vpn-border text-slate-400 hover:text-vpn-green hover:border-vpn-green/40 hover:bg-vpn-green/5"
          onClick={onOpenSettings}
        >
          ⚙️
        </Button>
      </div>
    </div>
  );
}

// ── SetupRequiredBanner — warning strip in the main content area ───────────────

export function SetupRequiredBanner({ onOpen }: { onOpen: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-3 mt-3 flex items-center gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3"
    >
      <AlertTriangle className="h-5 w-5 shrink-0 text-amber-400" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-amber-300">VM bağlantısı yapılandırılmamış</p>
        <p className="text-xs text-amber-400/70 mt-0.5">
          SSH bilgilerini girmeden test çalıştıramazsın.
        </p>
      </div>
      <Button
        size="sm"
        className="shrink-0 bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 hover:text-amber-100 text-xs gap-1.5"
        onClick={onOpen}
      >
        ⚙️ Ayarla
      </Button>
    </motion.div>
  );
}

// ── SetupModal — full-screen modal shown on first launch ──────────────────────

interface SetupModalProps {
  open: boolean;
  onClose: () => void;
}

export function SetupModal({ open, onClose }: SetupModalProps) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-[60] bg-black/85 backdrop-blur-md"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.div
            className="fixed inset-0 z-[61] flex items-center justify-center p-4"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 320, damping: 28 }}
          >
            <div className="w-full max-w-sm rounded-2xl border border-amber-500/30 bg-vpn-card p-6 shadow-2xl space-y-5">
              {/* Icon + title */}
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-amber-500/20 p-2.5 shrink-0">
                  <AlertTriangle className="h-6 w-6 text-amber-400" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-100">İlk Kurulum Gerekli</h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Testleri başlatmadan önce VM bilgilerini gir
                  </p>
                </div>
              </div>

              {/* Steps */}
              <div className="rounded-xl bg-black/30 border border-vpn-border p-3.5 space-y-2 text-xs text-slate-400">
                {[
                  ["VM IP adreslerini", "gir (VM1, VM2, isteğe bağlı VM3)"],
                  ["SSH kullanıcı adını", "gir (genellikle ubuntu)"],
                  ["Kimlik doğrulama yöntemini", "seç (şifre veya SSH key)"],
                  ['"Kaydet & Bağlantıyı Test Et"', "butonuna bas"],
                ].map(([bold, rest], i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="mt-0.5 text-vpn-green font-bold shrink-0">{i + 1}.</span>
                    <p>
                      <span className="text-slate-300 font-medium">{bold}</span>{" "}{rest}
                    </p>
                  </div>
                ))}
              </div>

              {/* CTA */}
              <Button
                className="w-full bg-vpn-green/20 border border-vpn-green/40 text-vpn-green hover:bg-vpn-green/30 gap-2 font-semibold"
                onClick={onClose}
              >
                ⚙️ VM Ayarlarını Aç →
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
