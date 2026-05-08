import { useState, useEffect } from "react";
import { Shield, Moon, Sun, Settings } from "lucide-react";
import { useStore } from "@/store";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { ControlPanel } from "@/components/ControlPanel";
import { StatusIndicator } from "@/components/StatusIndicator";
import { PhaseLog } from "@/components/PhaseLog";
import { SettingsPanel } from "@/components/SettingsPanel";
import { ConnectivityStatusCard, SetupModal } from "@/components/SetupWizard";
import { api } from "@/services/api";

export function Sidebar() {
  const darkMode = useStore((s) => s.darkMode);
  const toggleDarkMode = useStore((s) => s.toggleDarkMode);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [setupModalOpen, setSetupModalOpen] = useState(false);
  const [configured, setConfigured] = useState<boolean | null>(null); // null = loading

  // On mount: fetch config and decide whether to show setup wizard
  useEffect(() => {
    api.getConfig().then((cfg) => {
      setConfigured(cfg.configured);
      if (!cfg.configured) {
        // Delay so the app renders first, then the modal appears
        setTimeout(() => setSetupModalOpen(true), 600);
      }
    }).catch(() => {
      // Backend not reachable — still show the setup modal
      setConfigured(false);
      setTimeout(() => setSetupModalOpen(true), 600);
    });
  }, []);

  const openSettings = () => {
    setSetupModalOpen(false);
    setSettingsOpen(true);
  };

  return (
    <>
      <aside className="flex h-screen w-[280px] shrink-0 flex-col border-r border-vpn-border bg-vpn-card overflow-hidden transition-colors">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-vpn-border">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-vpn-green" />
            <div>
              <p className="text-sm font-bold text-foreground leading-none">VPN Benchmark</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">Suite v1.0</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Settings button */}
            <button
              onClick={() => setSettingsOpen(true)}
              className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-vpn-green transition-colors"
              title="Infrastructure Settings"
            >
              <Settings className="h-4 w-4" />
            </button>
            {/* Dark mode toggle */}
            <div className="flex items-center gap-1.5">
              {darkMode ? (
                <Moon className="h-3.5 w-3.5 text-slate-400" />
              ) : (
                <Sun className="h-3.5 w-3.5 text-vpn-orange" />
              )}
              <Switch
                checked={darkMode}
                onCheckedChange={toggleDarkMode}
                aria-label="Toggle dark mode"
              />
            </div>
          </div>
        </div>

        {/* Not-configured banner inside sidebar */}
        {configured === false && (
          <div className="px-4 pt-3">
            <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2.5 flex items-center gap-2">
              <span className="text-amber-400 text-base">⚠️</span>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-amber-300 leading-tight">Yapılandırılmamış</p>
                <button
                  className="text-[10px] text-amber-400/80 hover:text-amber-300 underline underline-offset-2"
                  onClick={openSettings}
                >
                  VM ayarlarını aç →
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          <ControlPanel />
          <Separator />

          {/* Live connectivity status */}
          <ConnectivityStatusCard onOpenSettings={openSettings} />

          <Separator />
          <StatusIndicator />
          <Separator />
          <PhaseLog />
        </div>
      </aside>

      {/* Setup wizard modal — auto-shown when not configured */}
      <SetupModal
        open={setupModalOpen}
        onClose={openSettings}
      />

      {/* Settings panel — slides in from right */}
      <SettingsPanel
        open={settingsOpen}
        onClose={() => {
          setSettingsOpen(false);
          // Re-check configured state after closing settings
          api.getConfig().then((cfg) => setConfigured(cfg.configured)).catch(() => {});
        }}
      />
    </>
  );
}
