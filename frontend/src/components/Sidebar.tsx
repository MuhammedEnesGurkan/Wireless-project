import { useState } from "react";
import { Shield, Moon, Sun, Settings } from "lucide-react";
import { useStore } from "@/store";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { ControlPanel } from "@/components/ControlPanel";
import { StatusIndicator } from "@/components/StatusIndicator";
import { PhaseLog } from "@/components/PhaseLog";
import { SettingsPanel } from "@/components/SettingsPanel";

export function Sidebar() {
  const darkMode = useStore((s) => s.darkMode);
  const toggleDarkMode = useStore((s) => s.toggleDarkMode);
  const [settingsOpen, setSettingsOpen] = useState(false);

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

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          <ControlPanel />
          <Separator />
          <StatusIndicator />
          <Separator />
          <PhaseLog />
        </div>
      </aside>

      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  );
}
