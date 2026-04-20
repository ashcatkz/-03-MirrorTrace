"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { generateRevenueData } from "@/lib/mock-data";
import { formatCurrency } from "@/lib/utils";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border/60 bg-card/95 backdrop-blur p-3 shadow-xl text-xs">
      <p className="font-semibold text-foreground mb-2">{label}</p>
      {payload.map((entry: any) => (
        <div key={entry.name} className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full" style={{ background: entry.color }} />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium text-foreground">
            {entry.name === "Revenus" ? formatCurrency(entry.value) : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
};

export function RevenueChart() {
  const data = useMemo(() => generateRevenueData(), []);
  const [view, setView] = useState<"area" | "bar">("area");

  return (
    <Card className="glass-card">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-semibold">
              Revenus quotidiens
            </CardTitle>
            <CardDescription className="text-xs mt-1">
              30 derniers jours — mise à jour en temps réel
            </CardDescription>
          </div>
          <div className="flex gap-1">
            <Button
              variant={view === "area" ? "gold-outline" : "ghost"}
              size="sm"
              className="h-7 text-xs px-3"
              onClick={() => setView("area")}
            >
              Aire
            </Button>
            <Button
              variant={view === "bar" ? "gold-outline" : "ghost"}
              size="sm"
              className="h-7 text-xs px-3"
              onClick={() => setView("bar")}
            >
              Barres
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pb-4">
        <ResponsiveContainer width="100%" height={220}>
          {view === "area" ? (
            <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="goldGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#C9A84C" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#C9A84C" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="emeraldGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10B981" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(224 14% 16%)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "hsl(215 20% 55%)" }}
                tickLine={false}
                axisLine={false}
                interval={6}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "hsl(215 20% 55%)" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${v / 1000}k`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="revenue"
                name="Revenus"
                stroke="#C9A84C"
                strokeWidth={2}
                fill="url(#goldGrad)"
                dot={false}
                activeDot={{ r: 4, fill: "#C9A84C" }}
              />
            </AreaChart>
          ) : (
            <BarChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(224 14% 16%)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "hsl(215 20% 55%)" }}
                tickLine={false}
                axisLine={false}
                interval={6}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "hsl(215 20% 55%)" }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                wrapperStyle={{ fontSize: 11, color: "hsl(215 20% 55%)" }}
              />
              <Bar dataKey="prospects" name="Prospects" fill="#C9A84C" radius={[3, 3, 0, 0]} opacity={0.8} />
              <Bar dataKey="conversions" name="Conversions" fill="#10B981" radius={[3, 3, 0, 0]} opacity={0.8} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
