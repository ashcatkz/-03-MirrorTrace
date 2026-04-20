"use client";

import { TrendingUp, Users, Mail, CheckCircle2, Zap, Euro } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { formatCurrency } from "@/lib/utils";
import { DASHBOARD_STATS } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  trend?: number;
  accent?: "gold" | "emerald" | "amber" | "default";
  pulse?: boolean;
}

function StatCard({ label, value, sub, icon: Icon, trend, accent = "default", pulse }: StatCardProps) {
  const accentClasses = {
    gold: "text-gold-light",
    emerald: "text-emerald-400",
    amber: "text-amber-400",
    default: "text-muted-foreground",
  };

  const iconBg = {
    gold: "bg-gold/10 text-gold-light",
    emerald: "bg-emerald-brand/10 text-emerald-400",
    amber: "bg-amber-500/10 text-amber-400",
    default: "bg-secondary text-muted-foreground",
  };

  return (
    <Card className="glass-card hover:border-gold/20 transition-all duration-300 group">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              {label}
            </p>
            <div className="flex items-baseline gap-2">
              <p className={cn("text-2xl font-bold", accentClasses[accent])}>{value}</p>
              {trend !== undefined && (
                <span className={cn("text-xs font-medium", trend >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {trend >= 0 ? "+" : ""}{trend}%
                </span>
              )}
            </div>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
          <div className={cn("rounded-lg p-2.5", iconBg[accent])}>
            <Icon className={cn("h-5 w-5", pulse && "animate-pulse-gold")} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function StatsCards() {
  const stats = DASHBOARD_STATS;

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
      <StatCard
        label="Prospects"
        value={stats.totalProspects.toLocaleString("fr-FR")}
        sub={`+${stats.newToday} aujourd'hui`}
        icon={Users}
        trend={12}
        accent="default"
        pulse
      />
      <StatCard
        label="Emails envoyés"
        value={stats.emailsSent.toLocaleString("fr-FR")}
        icon={Mail}
        trend={8}
        accent="amber"
      />
      <StatCard
        label="Paiements"
        value={stats.paymentsReceived.toLocaleString("fr-FR")}
        sub="Ce mois"
        icon={CheckCircle2}
        trend={23}
        accent="emerald"
      />
      <StatCard
        label="Conversion"
        value={`${stats.conversionRate}%`}
        sub="Taux moyen"
        icon={TrendingUp}
        trend={5}
        accent="gold"
      />
      <StatCard
        label="Revenus / jour"
        value={formatCurrency(stats.dailyRevenue)}
        icon={Zap}
        trend={15}
        accent="amber"
      />
      <StatCard
        label="Total revenus"
        value={formatCurrency(stats.totalRevenue)}
        sub="Cumulé"
        icon={Euro}
        trend={18}
        accent="emerald"
      />
    </div>
  );
}
