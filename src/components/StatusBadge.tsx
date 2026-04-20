"use client";

import { ProspectStatus } from "@/types/prospect";
import { Badge } from "@/components/ui/badge";
import { Target, Mail, CheckCircle2, XCircle } from "lucide-react";

const STATUS_CONFIG: Record<
  ProspectStatus,
  { label: string; variant: "gold" | "amber" | "emerald" | "red"; icon: React.ElementType }
> = {
  identified: {
    label: "Cible identifiée",
    variant: "gold",
    icon: Target,
  },
  email_sent: {
    label: "Email envoyé",
    variant: "amber",
    icon: Mail,
  },
  payment_received: {
    label: "Paiement reçu",
    variant: "emerald",
    icon: CheckCircle2,
  },
  lost: {
    label: "Perdu",
    variant: "red",
    icon: XCircle,
  },
};

interface StatusBadgeProps {
  status: ProspectStatus;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <Badge variant={config.variant} className={className}>
      <Icon className="h-3 w-3" />
      {config.label}
    </Badge>
  );
}

export { STATUS_CONFIG };
