import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatSiret(siret: string): string {
  return siret.replace(/(\d{3})(\d{3})(\d{3})(\d{5})/, "$1 $2 $3 $4");
}

export function formatCurrency(amount: number, currency = "EUR"): string {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function formatDate(dateStr: string): string {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(dateStr));
}

export function formatDateRelative(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "À l'instant";
  if (diffMins < 60) return `Il y a ${diffMins}min`;
  if (diffHours < 24) return `Il y a ${diffHours}h`;
  if (diffDays === 1) return "Hier";
  return formatDate(dateStr);
}

export const NAF_LABELS: Record<string, string> = {
  "6201Z": "Programmation informatique",
  "6202A": "Conseil en systèmes informatiques",
  "7022Z": "Conseil pour les affaires et management",
  "7490B": "Activités spécialisées diverses",
  "8211Z": "Services administratifs combinés",
  "6920Z": "Activités comptables",
  "7311Z": "Activités des agences de publicité",
  "4791A": "Vente à distance",
  "5610A": "Restauration traditionnelle",
  "4120A": "Construction de maisons individuelles",
};

export function getNafLabel(code: string): string {
  return NAF_LABELS[code] ?? "Activité commerciale";
}
