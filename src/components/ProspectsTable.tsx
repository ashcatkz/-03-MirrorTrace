"use client";

import { useState } from "react";
import {
  Building2,
  User,
  MapPin,
  Calendar,
  Brain,
  FileText,
  ChevronDown,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge, STATUS_CONFIG } from "@/components/StatusBadge";
import { useProspectsStore } from "@/store/prospects";
import { Prospect, ProspectStatus } from "@/types/prospect";
import { formatDate, formatDateRelative, formatCurrency, formatSiret, cn } from "@/lib/utils";
import { generateInvoicePDF } from "@/lib/pdf";

const STATUS_OPTIONS: Array<{ value: ProspectStatus | "all"; label: string }> = [
  { value: "all", label: "Tous" },
  { value: "identified", label: "Cible identifiée" },
  { value: "email_sent", label: "Email envoyé" },
  { value: "payment_received", label: "Paiement reçu" },
  { value: "lost", label: "Perdu" },
];

function StatusDropdown({ prospect }: { prospect: Prospect }) {
  const [open, setOpen] = useState(false);
  const { updateStatus } = useProspectsStore();

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 focus:outline-none group"
      >
        <StatusBadge status={prospect.status} />
        <ChevronDown className={cn(
          "h-3 w-3 text-muted-foreground transition-transform",
          open && "rotate-180"
        )} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-full z-20 mt-1 w-44 rounded-lg border border-border bg-card shadow-xl animate-slide-in">
            {(Object.keys(STATUS_CONFIG) as ProspectStatus[]).map((status) => {
              const cfg = STATUS_CONFIG[status];
              const Icon = cfg.icon;
              return (
                <button
                  key={status}
                  onClick={() => { updateStatus(prospect.id, status); setOpen(false); }}
                  className={cn(
                    "flex w-full items-center gap-2 px-3 py-2 text-xs hover:bg-accent transition-colors first:rounded-t-lg last:rounded-b-lg",
                    prospect.status === status && "bg-accent"
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {cfg.label}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function ProspectRow({ prospect }: { prospect: Prospect }) {
  const [expanded, setExpanded] = useState(false);
  const { markInvoiceGenerated } = useProspectsStore();

  const handleGeneratePDF = async () => {
    await generateInvoicePDF(prospect);
    markInvoiceGenerated(prospect.id);
  };

  return (
    <>
      <tr
        className={cn(
          "border-b border-border/40 hover:bg-accent/30 transition-colors cursor-pointer group",
          expanded && "bg-accent/20"
        )}
        onClick={() => setExpanded(!expanded)}
      >
        {/* Entreprise */}
        <td className="px-4 py-3">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-md bg-secondary p-1.5 group-hover:bg-gold/10 transition-colors">
              <Building2 className="h-3.5 w-3.5 text-muted-foreground group-hover:text-gold-light transition-colors" />
            </div>
            <div>
              <p className="font-medium text-sm text-foreground leading-tight">
                {prospect.companyName}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5 font-mono">
                {formatSiret(prospect.siret)}
              </p>
            </div>
          </div>
        </td>

        {/* Dirigeant */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <User className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <span className="text-sm text-foreground">{prospect.directorName}</span>
          </div>
        </td>

        {/* Code NAF */}
        <td className="px-4 py-3">
          <div>
            <Badge variant="outline" className="font-mono text-xs px-2 py-0.5 border-border/60">
              {prospect.nafCode}
            </Badge>
            <p className="text-xs text-muted-foreground mt-1 max-w-[140px] truncate">
              {prospect.nafLabel}
            </p>
          </div>
        </td>

        {/* Localisation */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5">
            <MapPin className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <div>
              <p className="text-sm text-foreground">{prospect.city}</p>
              <p className="text-xs text-muted-foreground">{prospect.postalCode}</p>
            </div>
          </div>
        </td>

        {/* Date création */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <div>
              <p className="text-sm text-foreground">{formatDate(prospect.createdAt)}</p>
              <p className="text-xs text-muted-foreground">{formatDateRelative(prospect.scrapedAt)}</p>
            </div>
          </div>
        </td>

        {/* Revenus estimés */}
        <td className="px-4 py-3">
          {prospect.estimatedRevenue ? (
            <div>
              <p className="text-sm font-semibold gold-text">
                {formatCurrency(prospect.estimatedRevenue)}
              </p>
              <p className="text-xs text-muted-foreground">/mois</p>
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </td>

        {/* Statut */}
        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
          <StatusDropdown prospect={prospect} />
        </td>

        {/* Actions */}
        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
          <Button
            variant="gold"
            size="sm"
            className="h-7 text-xs px-3 whitespace-nowrap"
            onClick={handleGeneratePDF}
            disabled={prospect.invoiceGenerated}
          >
            <FileText className="h-3 w-3" />
            {prospect.invoiceGenerated ? "Générée" : "Facture PDF"}
          </Button>
        </td>
      </tr>

      {/* Expanded row — AI insight */}
      {expanded && (
        <tr className="border-b border-border/40 bg-accent/10 animate-slide-in">
          <td colSpan={8} className="px-4 py-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {/* AI Insight */}
              <div className="flex gap-3 rounded-lg border border-gold/20 bg-gold/5 p-3">
                <Brain className="h-4 w-4 text-gold-light mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-gold-light mb-1">Analyse IA</p>
                  <p className="text-sm text-foreground/90">{prospect.aiInsight}</p>
                </div>
              </div>

              {/* Mission recommandée */}
              <div className="flex gap-3 rounded-lg border border-border/60 bg-secondary/50 p-3">
                <ExternalLink className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-semibold text-muted-foreground mb-1">Mission recommandée</p>
                  <p className="text-sm text-foreground/90">{prospect.accountingNeed}</p>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export function ProspectsTable() {
  const { filter, setFilter, searchQuery, setSearchQuery, filteredProspects } =
    useProspectsStore();

  const prospects = filteredProspects();

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-1 flex-wrap">
          {STATUS_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setFilter(value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                filter === value
                  ? "gold-gradient text-[#1a1206] shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent"
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <input
          type="text"
          placeholder="Rechercher..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="h-8 w-full max-w-[240px] rounded-lg border border-input bg-secondary/50 px-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring transition-all"
        />
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-border/60">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/60 bg-secondary/30">
              {[
                "Entreprise",
                "Dirigeant",
                "Code NAF",
                "Localisation",
                "Date création",
                "Revenu est.",
                "Statut",
                "Actions",
              ].map((col) => (
                <th
                  key={col}
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {prospects.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-16 text-center text-muted-foreground text-sm">
                  Aucun prospect trouvé
                </td>
              </tr>
            ) : (
              prospects.map((p) => <ProspectRow key={p.id} prospect={p} />)
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-muted-foreground text-right">
        {prospects.length} prospect{prospects.length > 1 ? "s" : ""} affiché{prospects.length > 1 ? "s" : ""}
      </p>
    </div>
  );
}
