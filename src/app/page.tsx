"use client";

import { Crosshair, Sparkles, TrendingUp, Bell } from "lucide-react";
import { StatsCards } from "@/components/StatsCards";
import { RevenueChart } from "@/components/RevenueChart";
import { ProspectsTable } from "@/components/ProspectsTable";
import { ScraperControl } from "@/components/ScraperControl";
import { Badge } from "@/components/ui/badge";
import { useProspectsStore } from "@/store/prospects";
import { useAutoRefresh } from "@/hooks/useAutoRefresh";

function Header() {
  const { isScraping, prospects } = useProspectsStore();
  const newCount = prospects.filter(
    (p) => new Date(p.scrapedAt) > new Date(Date.now() - 3600000)
  ).length;

  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-screen-2xl items-center justify-between px-6">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg gold-gradient">
            <Crosshair className="h-4 w-4 text-[#1a1206]" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-bold text-base tracking-tight gold-text">MirrorTrace</span>
            <Badge variant="outline" className="h-4 px-1.5 text-[10px] border-gold/20 text-gold-light/60">
              v1.0
            </Badge>
          </div>
        </div>

        {/* Center — live indicator */}
        {isScraping && (
          <div className="flex items-center gap-2 rounded-full border border-emerald-brand/20 bg-emerald-brand/5 px-3 py-1">
            <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_4px_rgba(52,211,153,0.8)]" />
            <span className="text-xs text-emerald-400 font-medium">
              Surveillance en temps réel
            </span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3">
          {newCount > 0 && (
            <div className="relative">
              <Bell className="h-4 w-4 text-muted-foreground" />
              <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-gold text-[9px] font-bold text-[#1a1206]">
                {newCount}
              </span>
            </div>
          )}
          <ScraperControl />
        </div>
      </div>
    </header>
  );
}

function SectionHeader({
  icon: Icon,
  title,
  sub,
}: {
  icon: React.ElementType;
  title: string;
  sub?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gold/10">
        <Icon className="h-4 w-4 text-gold-light" />
      </div>
      <div>
        <h2 className="font-semibold text-sm text-foreground">{title}</h2>
        {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  useAutoRefresh(30000);
  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="mx-auto max-w-screen-2xl px-6 py-8 space-y-8">
        {/* Hero greeting */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              Dashboard de Prospection
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Surveillance automatisée des nouvelles immatriculations — Powered by GPT-4
            </p>
          </div>
          <div className="hidden lg:flex items-center gap-2 text-xs text-muted-foreground bg-secondary/50 border border-border/60 rounded-lg px-3 py-2">
            <Sparkles className="h-3.5 w-3.5 text-gold-light" />
            Curation IA active
          </div>
        </div>

        {/* KPI Cards */}
        <StatsCards />

        {/* Chart */}
        <div>
          <SectionHeader
            icon={TrendingUp}
            title="Performance financière"
            sub="Revenus et conversions — 30 derniers jours"
          />
          <div className="mt-4">
            <RevenueChart />
          </div>
        </div>

        {/* Table */}
        <div>
          <SectionHeader
            icon={Crosshair}
            title="Tableau de chasse"
            sub="Nouvelles immatriculations détectées — cliquer sur une ligne pour l'analyse IA"
          />
          <div className="mt-4">
            <ProspectsTable />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/40 mt-8">
        <div className="mx-auto max-w-screen-2xl px-6 py-4 flex items-center justify-between text-xs text-muted-foreground">
          <span>MirrorTrace © 2025 — Projet de recherche sur l'automatisation commerciale</span>
          <div className="flex items-center gap-1.5">
            <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span>Données Pappers / INSEE Sirene</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
