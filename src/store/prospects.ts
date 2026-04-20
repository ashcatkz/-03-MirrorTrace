import { create } from "zustand";
import { Prospect, ProspectStatus } from "@/types/prospect";
import { MOCK_PROSPECTS } from "@/lib/mock-data";

interface ProspectsStore {
  prospects: Prospect[];
  selectedProspect: Prospect | null;
  isLoading: boolean;
  isScraping: boolean;
  filter: ProspectStatus | "all";
  searchQuery: string;

  setFilter: (filter: ProspectStatus | "all") => void;
  setSearchQuery: (q: string) => void;
  selectProspect: (p: Prospect | null) => void;
  updateStatus: (id: string, status: ProspectStatus) => void;
  addProspects: (prospects: Prospect[]) => void;
  setIsScraping: (v: boolean) => void;
  markInvoiceGenerated: (id: string) => void;

  filteredProspects: () => Prospect[];
}

export const useProspectsStore = create<ProspectsStore>((set, get) => ({
  prospects: MOCK_PROSPECTS,
  selectedProspect: null,
  isLoading: false,
  isScraping: false,
  filter: "all",
  searchQuery: "",

  setFilter: (filter) => set({ filter }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  selectProspect: (selectedProspect) => set({ selectedProspect }),
  setIsScraping: (isScraping) => set({ isScraping }),

  updateStatus: (id, status) =>
    set((state) => ({
      prospects: state.prospects.map((p) =>
        p.id === id ? { ...p, status } : p
      ),
    })),

  addProspects: (newProspects) =>
    set((state) => {
      const existingSirets = new Set(state.prospects.map((p) => p.siret));
      const fresh = newProspects.filter(
        (p) => p.siret && p.companyName && !existingSirets.has(p.siret)
      );
      if (fresh.length === 0) return state;
      return { prospects: [...fresh, ...state.prospects] };
    }),

  markInvoiceGenerated: (id) =>
    set((state) => ({
      prospects: state.prospects.map((p) =>
        p.id === id ? { ...p, invoiceGenerated: true } : p
      ),
    })),

  filteredProspects: () => {
    const { prospects, filter, searchQuery } = get();
    return prospects.filter((p) => {
      const matchesFilter = filter === "all" || p.status === filter;
      const q = searchQuery.toLowerCase();
      const matchesSearch =
        !q ||
        p.companyName.toLowerCase().includes(q) ||
        p.directorName.toLowerCase().includes(q) ||
        p.nafCode.toLowerCase().includes(q) ||
        p.city.toLowerCase().includes(q);
      return matchesFilter && matchesSearch;
    });
  },
}));
