"use client";

import { useState } from "react";
import { Play, Square, RefreshCw, Wifi, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useProspectsStore } from "@/store/prospects";
import { cn } from "@/lib/utils";

export function ScraperControl() {
  const { isScraping, setIsScraping, addProspects } = useProspectsStore();
  const [lastSync, setLastSync] = useState<Date | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const toggleScraper = async () => {
    if (isScraping) {
      setIsScraping(false);
      return;
    }
    setIsScraping(true);
    try {
      const resp = await fetch("/api/scraper/trigger", { method: "POST" });
      const data = await resp.json();
      if (data.prospects?.length) {
        addProspects(data.prospects);
        setLastSync(new Date());
      }
    } catch {
      // silently handle — scraper may be starting in background
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      const resp = await fetch("/api/prospects");
      const data = await resp.json();
      if (data.prospects) addProspects(data.prospects);
      setLastSync(new Date());
    } catch {
      // ignore
    } finally {
      setTimeout(() => setIsRefreshing(false), 800);
    }
  };

  return (
    <div className="flex items-center gap-3">
      {/* Status indicator */}
      <div className="flex items-center gap-2">
        <div className={cn(
          "h-2 w-2 rounded-full",
          isScraping
            ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)] animate-pulse"
            : "bg-muted-foreground/40"
        )} />
        <span className="text-xs text-muted-foreground hidden sm:block">
          {isScraping ? "Surveillance active" : "En pause"}
        </span>
      </div>

      {lastSync && (
        <span className="text-xs text-muted-foreground hidden md:block">
          Sync: {lastSync.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
        </span>
      )}

      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={handleRefresh}
        disabled={isRefreshing}
      >
        <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
      </Button>

      <Button
        variant={isScraping ? "outline" : "gold"}
        size="sm"
        onClick={toggleScraper}
        className="h-8 gap-2"
      >
        {isScraping ? (
          <>
            <Square className="h-3 w-3" />
            <span className="hidden sm:inline">Arrêter</span>
          </>
        ) : (
          <>
            <Play className="h-3 w-3" />
            <span className="hidden sm:inline">Lancer scraper</span>
          </>
        )}
      </Button>
    </div>
  );
}
