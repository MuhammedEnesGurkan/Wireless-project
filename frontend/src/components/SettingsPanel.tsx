import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X, Settings, Save, Wifi, WifiOff, Loader2, Eye, EyeOff, CheckCircle2, XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { api, type VmSettings, type ConnectivityResult } from "@/services/api";
import { cn } from "@/lib/utils";

// ── Simple input wrapper (no shadcn Input component was generated, use raw with vpn styles) ──
interface FieldProps {
  label: string;
  value: string | number;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  hint?: string;
  disabled?: boolean;
}

function Field({ label, value, onChange, placeholder, type = "text", hint, disabled }: FieldProps) {
  const [show, setShow] = useState(false);
  const isPassword = type === "password";
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-slate-400">{label}</label>
      <div className="relative">
        <input
          type={isPassword && !show ? "password" : "text"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          className={cn(
            "w-full rounded-md border border-vpn-border bg-black/30 px-3 py-2 text-sm text-slate-200",
            "placeholder:text-slate-600 focus:border-vpn-green focus:outline-none transition-colors",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            isPassword && "pr-9",
          )}
        />
        {isPassword && (
          <button
            type="button"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            onClick={() => setShow((s) => !s)}
          >
            {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>
      {hint && <p className="text-[10px] text-slate-600">{hint}</p>}
    </div>
  );
}

// ── Toggle between key / password auth ────────────────────────────────────────
interface AuthToggleProps {
  usePassword: boolean;
  onToggle: (v: boolean) => void;
}
function AuthToggle({ usePassword, onToggle }: AuthToggleProps) {
  return (
    <div className="flex rounded-md border border-vpn-border overflow-hidden text-xs">
      <button
        className={cn(
          "flex-1 py-1.5 transition-colors",
          !usePassword ? "bg-vpn-green text-white font-medium" : "text-slate-400 hover:text-slate-200",
        )}
        onClick={() => onToggle(false)}
      >
        🔑 SSH Key
      </button>
      <button
        className={cn(
          "flex-1 py-1.5 transition-colors",
          usePassword ? "bg-vpn-blue text-white font-medium" : "text-slate-400 hover:text-slate-200",
        )}
        onClick={() => onToggle(true)}
      >
        🔐 Password
      </button>
    </div>
  );
}

// ── VM config block ────────────────────────────────────────────────────────────
interface VmBlockProps {
  label: string;
  color: string;
  vm: VmSettings;
  result?: ConnectivityResult;
  onChange: (updated: VmSettings) => void;
  disabled?: boolean;
}

function VmBlock({ label, color, vm, result, onChange, disabled }: VmBlockProps) {
  return (
    <div className="rounded-lg border border-vpn-border bg-black/20 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold" style={{ color }}>
          {label}
        </span>
        {result && (
          <Badge variant={result.success ? "success" : "destructive"} className="text-[10px] gap-1">
            {result.success ? (
              <><CheckCircle2 className="h-2.5 w-2.5" /> {result.latency_ms}ms</>
            ) : (
              <><XCircle className="h-2.5 w-2.5" /> Failed</>
            )}
          </Badge>
        )}
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-2">
          <Field
            label="IP / Hostname"
            value={vm.host}
            onChange={(v) => onChange({ ...vm, host: v })}
            placeholder="192.168.56.10"
            disabled={disabled}
          />
        </div>
        <Field
          label="SSH Port"
          value={vm.port}
          onChange={(v) => onChange({ ...vm, port: parseInt(v) || 22 })}
          placeholder="22"
          disabled={disabled}
        />
      </div>

      <Field
        label="SSH Username"
        value={vm.user}
        onChange={(v) => onChange({ ...vm, user: v })}
        placeholder="ubuntu"
        disabled={disabled}
      />

      <AuthToggle
        usePassword={vm.use_password_auth}
        onToggle={(v) => onChange({ ...vm, use_password_auth: v })}
      />

      {vm.use_password_auth ? (
        <Field
          label="SSH Password"
          value={vm.ssh_password ?? ""}
          onChange={(v) => onChange({ ...vm, ssh_password: v })}
          placeholder="••••••••"
          type="password"
          disabled={disabled}
        />
      ) : (
        <Field
          label="SSH Key Path"
          value={vm.ssh_key_path}
          onChange={(v) => onChange({ ...vm, ssh_key_path: v })}
          placeholder="~/.ssh/id_rsa"
          hint="Absolute or ~ path to the private key file on this host machine"
          disabled={disabled}
        />
      )}

      {result && !result.success && (
        <p className="text-[10px] text-red-400 font-mono break-all">{result.message}</p>
      )}
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

const DEFAULT_VM: VmSettings = {
  host: "",
  port: 22,
  user: "ubuntu",
  ssh_key_path: "",
  ssh_password: "",
  use_password_auth: false,
};

export function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const [vm1, setVm1] = useState<VmSettings>({ ...DEFAULT_VM });
  const [vm2, setVm2] = useState<VmSettings>({ ...DEFAULT_VM });
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [results, setResults] = useState<ConnectivityResult[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Load current config on open
  useEffect(() => {
    if (!open) return;
    api.getConfig().then((cfg) => {
      setVm1({
        host: cfg.vm1.host,
        port: cfg.vm1.port,
        user: cfg.vm1.user,
        ssh_key_path: cfg.vm1.ssh_key_path,
        ssh_password: "",
        use_password_auth: cfg.vm1.use_password_auth,
      });
      setVm2({
        host: cfg.vm2.host,
        port: cfg.vm2.port,
        user: cfg.vm2.user,
        ssh_key_path: cfg.vm2.ssh_key_path,
        ssh_password: "",
        use_password_auth: cfg.vm2.use_password_auth,
      });
      setResults([]);
      setSaveError(null);
      setSaved(false);
    }).catch(() => {});
  }, [open]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      await api.saveConfig({ vm1, vm2 });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }, [vm1, vm2]);

  const handleTestConnectivity = useCallback(async () => {
    // Save first, then test
    setSaving(true);
    setSaveError(null);
    try {
      await api.saveConfig({ vm1, vm2 });
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
      setSaving(false);
      return;
    }
    setSaving(false);

    setTesting(true);
    setResults([]);
    try {
      const res = await api.testConnectivity();
      setResults(res);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setTesting(false);
    }
  }, [vm1, vm2]);

  const vm1Result = results.find((r) => r.vm === "vm1");
  const vm2Result = results.find((r) => r.vm === "vm2");
  const allOk = results.length === 2 && results.every((r) => r.success);

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            className="fixed right-0 top-0 z-50 flex h-screen w-[480px] flex-col border-l border-vpn-border bg-vpn-card shadow-2xl"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-vpn-border px-5 py-4">
              <div className="flex items-center gap-2">
                <Settings className="h-4 w-4 text-vpn-green" />
                <span className="font-semibold text-slate-100">Infrastructure Settings</span>
              </div>
              <button
                className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-slate-200 transition-colors"
                onClick={onClose}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 scrollbar-thin">
              <p className="text-xs text-slate-500">
                Enter SSH credentials for both VMs. These settings override{" "}
                <code className="text-slate-400">config.yaml</code> at runtime — no restart needed.
              </p>

              <VmBlock
                label="VM1 — VPN Server"
                color="#22c55e"
                vm={vm1}
                result={vm1Result}
                onChange={setVm1}
                disabled={saving || testing}
              />

              <VmBlock
                label="VM2 — VPN Client / Test Engine"
                color="#3b82f6"
                vm={vm2}
                result={vm2Result}
                onChange={setVm2}
                disabled={saving || testing}
              />

              {saveError && (
                <Alert variant="destructive">
                  <AlertDescription className="text-xs font-mono break-all">
                    {saveError}
                  </AlertDescription>
                </Alert>
              )}

              {allOk && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-2 rounded-lg border border-vpn-green/30 bg-vpn-green/10 px-3 py-2 text-xs text-vpn-green"
                >
                  <Wifi className="h-4 w-4 shrink-0" />
                  Both VMs reachable — you're ready to run tests!
                </motion.div>
              )}

              {results.length > 0 && !allOk && (
                <div className="space-y-1">
                  {results.filter((r) => !r.success).map((r) => (
                    <div key={r.vm} className="flex items-center gap-2 text-xs text-red-400">
                      <WifiOff className="h-3.5 w-3.5 shrink-0" />
                      {r.vm.toUpperCase()} — {r.message}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="border-t border-vpn-border px-5 py-4 space-y-2">
              <Button
                variant="outline"
                className="w-full gap-2 border-vpn-border text-slate-300 hover:bg-white/5"
                onClick={handleTestConnectivity}
                disabled={saving || testing || !vm1.host || !vm2.host}
              >
                {testing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Wifi className="h-4 w-4" />
                )}
                {testing ? "Testing…" : "Save & Test Connectivity"}
              </Button>

              <Button
                variant="success"
                className="w-full gap-2"
                onClick={handleSave}
                disabled={saving || testing || !vm1.host || !vm2.host}
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : saved ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {saved ? "Saved!" : saving ? "Saving…" : "Save Settings"}
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
