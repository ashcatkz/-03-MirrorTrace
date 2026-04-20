import { Prospect } from "@/types/prospect";
import { formatCurrency, formatDate, formatSiret } from "@/lib/utils";

export async function generateInvoicePDF(prospect: Prospect): Promise<void> {
  // Dynamic import to avoid SSR issues
  const { default: jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");

  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const now = new Date();
  const invoiceNumber = `MT-${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}-${prospect.id.padStart(4, "0")}`;

  const GOLD = [201, 168, 76] as [number, number, number];
  const DARK = [15, 18, 28] as [number, number, number];
  const MUTED = [120, 130, 150] as [number, number, number];
  const WHITE = [255, 255, 255] as [number, number, number];

  // Background
  doc.setFillColor(...DARK);
  doc.rect(0, 0, 210, 297, "F");

  // Gold accent bar
  doc.setFillColor(...GOLD);
  doc.rect(0, 0, 8, 297, "F");

  // Header zone
  doc.setFillColor(25, 28, 42);
  doc.roundedRect(18, 12, 174, 50, 4, 4, "F");

  // Logo/Brand
  doc.setFont("helvetica", "bold");
  doc.setFontSize(22);
  doc.setTextColor(...GOLD);
  doc.text("MirrorTrace", 28, 30);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text("Plateforme de Prospection Automatisée", 28, 37);

  // Invoice meta (right side)
  doc.setFont("helvetica", "bold");
  doc.setFontSize(14);
  doc.setTextColor(...WHITE);
  doc.text("FACTURE", 162, 28, { align: "right" });

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text(`N° ${invoiceNumber}`, 162, 35, { align: "right" });
  doc.text(`Date: ${formatDate(now.toISOString())}`, 162, 41, { align: "right" });
  doc.text(`Échéance: ${formatDate(new Date(now.getTime() + 30 * 86400000).toISOString())}`, 162, 47, { align: "right" });

  // Client section
  doc.setFillColor(25, 28, 42);
  doc.roundedRect(18, 72, 80, 55, 4, 4, "F");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(7);
  doc.setTextColor(...GOLD);
  doc.text("CLIENT", 26, 83);

  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(...WHITE);
  doc.text(prospect.companyName, 26, 92);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text(`Dirigeant: ${prospect.directorName}`, 26, 100);
  doc.text(`SIRET: ${formatSiret(prospect.siret)}`, 26, 107);
  doc.text(`${prospect.address}`, 26, 114);
  doc.text(`${prospect.postalCode} ${prospect.city}`, 26, 121);

  // Emitter section
  doc.setFillColor(25, 28, 42);
  doc.roundedRect(110, 72, 82, 55, 4, 4, "F");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(7);
  doc.setTextColor(...GOLD);
  doc.text("ÉMETTEUR", 118, 83);

  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(...WHITE);
  doc.text("Cabinet MirrorTrace", 118, 92);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...MUTED);
  doc.text("Expert-Comptable & Conseil", 118, 100);
  doc.text("SIRET: 12345678900001", 118, 107);
  doc.text("12 Avenue des Champs-Élysées", 118, 114);
  doc.text("75008 Paris", 118, 121);

  // Services table
  const monthlyFee = prospect.estimatedRevenue ?? 1500;
  const setupFee = Math.round(monthlyFee * 0.5);
  const subtotal = monthlyFee + setupFee;
  const tva = Math.round(subtotal * 0.2);
  const total = subtotal + tva;

  autoTable(doc, {
    startY: 140,
    margin: { left: 18, right: 18 },
    head: [["Prestation", "Qté", "Prix unitaire HT", "Total HT"]],
    body: [
      [prospect.accountingNeed ?? "Mission comptable complète", "1 mois", formatCurrency(monthlyFee), formatCurrency(monthlyFee)],
      ["Frais d'entrée & paramétrage", "1", formatCurrency(setupFee), formatCurrency(setupFee)],
      ["Analyse IA & rapport personnalisé", "1", "Offert", "0 €"],
    ],
    foot: [
      ["", "", "Sous-total HT", formatCurrency(subtotal)],
      ["", "", "TVA (20%)", formatCurrency(tva)],
      ["", "", "Total TTC", formatCurrency(total)],
    ],
    styles: {
      fontSize: 8,
      cellPadding: 4,
      textColor: WHITE,
      fillColor: [25, 28, 42],
      lineColor: [40, 44, 60],
      lineWidth: 0.3,
    },
    headStyles: {
      fillColor: GOLD,
      textColor: [26, 18, 6],
      fontStyle: "bold",
      fontSize: 8,
    },
    footStyles: {
      fillColor: [20, 23, 35],
      textColor: WHITE,
      fontStyle: "bold",
      fontSize: 8,
    },
    alternateRowStyles: {
      fillColor: [20, 23, 35],
    },
  });

  // AI insight box
  const tableEndY = (doc as any).lastAutoTable.finalY + 10;
  doc.setFillColor(35, 30, 15);
  doc.setDrawColor(...GOLD);
  doc.setLineWidth(0.5);
  doc.roundedRect(18, tableEndY, 174, 25, 3, 3, "FD");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(7);
  doc.setTextColor(...GOLD);
  doc.text("ANALYSE IA — BESOIN IDENTIFIÉ", 26, tableEndY + 9);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...WHITE);
  const insight = prospect.aiInsight ?? "Mission comptable adaptée aux besoins de votre structure.";
  doc.text(doc.splitTextToSize(insight, 160), 26, tableEndY + 17);

  // Footer
  doc.setFont("helvetica", "normal");
  doc.setFontSize(7);
  doc.setTextColor(...MUTED);
  doc.text("Conditions de paiement: 30 jours net — Virement bancaire ou carte", 105, 275, { align: "center" });
  doc.text("IBAN: FR76 3000 6000 0112 3456 7890 189 — BIC: BNPAFRPP", 105, 280, { align: "center" });
  doc.text(`MirrorTrace © ${now.getFullYear()} — Tous droits réservés`, 105, 285, { align: "center" });

  doc.save(`Facture_${invoiceNumber}_${prospect.companyName.replace(/\s+/g, "_")}.pdf`);
}
