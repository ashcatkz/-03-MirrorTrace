export type ProspectStatus =
  | "identified"
  | "email_sent"
  | "payment_received"
  | "lost";

export interface Prospect {
  id: string;
  siret: string;
  siren: string;
  companyName: string;
  directorName: string;
  nafCode: string;
  nafLabel: string;
  createdAt: string;
  address: string;
  city: string;
  postalCode: string;
  email?: string;
  phone?: string;
  status: ProspectStatus;
  aiInsight?: string;
  accountingNeed?: string;
  estimatedRevenue?: number;
  invoiceGenerated?: boolean;
  notes?: string;
  scrapedAt: string;
}

export interface RevenueDataPoint {
  date: string;
  revenue: number;
  prospects: number;
  conversions: number;
}

export interface DashboardStats {
  totalProspects: number;
  emailsSent: number;
  paymentsReceived: number;
  conversionRate: number;
  dailyRevenue: number;
  totalRevenue: number;
  newToday: number;
}
