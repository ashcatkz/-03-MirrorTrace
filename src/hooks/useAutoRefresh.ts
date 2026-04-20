"use client";

import { useEffect, useRef } from "react";
import { useProspectsStore } from "@/store/prospects";
import { Prospect } from "@/types/prospect";

export function useAutoRefresh(intervalMs = 30000) {
  const { addProspects, prospects } = useProspectsStore();
  const knownIds = useRef(new Set(prospects.map((p) => p.siret)));

  useEffect(() => {
    const fetchNew = async () => {
      try {
        const resp = await fetch("/api/prospects/ingest");
        if (!resp.ok) return;
        const data = await resp.json();
        const incoming: Prospect[] = data.prospects ?? [];

        const fresh = incoming.filter((p) => !knownIds.current.has(p.siret));
        if (fresh.length > 0) {
          fresh.forEach((p) => knownIds.current.add(p.siret));
          addProspects(fresh);
        }
      } catch {
        // Silencieux — le scraper n'est peut-être pas actif
      }
    };

    const id = setInterval(fetchNew, intervalMs);
    return () => clearInterval(id);
  }, [addProspects, intervalMs]);
}
