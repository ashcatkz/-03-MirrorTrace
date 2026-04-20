import { NextResponse } from "next/server";

export async function POST() {
  // In production: this would spawn the Python scraper via a job queue
  // (e.g. Trigger.dev, BullMQ, or a simple shell exec on a VPS)
  // On Vercel: the Python scraper runs as a separate service/cron job

  // Simulate a scraper response with a fresh prospect
  const mockNewProspect = {
    id: crypto.randomUUID(),
    siret: `${Math.floor(Math.random() * 90000000000000) + 10000000000000}`,
    siren: `${Math.floor(Math.random() * 900000000) + 100000000}`,
    companyName: `NOUVELLE ENTREPRISE ${Math.floor(Math.random() * 999)} SAS`,
    directorName: "Nouveau Dirigeant",
    nafCode: "6201Z",
    nafLabel: "Programmation informatique",
    createdAt: new Date().toISOString(),
    address: "1 Rue de l'Innovation",
    city: "Paris",
    postalCode: "75001",
    status: "identified" as const,
    aiInsight: "Nouvelle société tech — besoin immédiat en comptabilité et gestion des SaaS.",
    accountingNeed: "Mise en place comptabilité + déclarations + conseil fiscal",
    estimatedRevenue: Math.floor(Math.random() * 2000) + 1000,
    scrapedAt: new Date().toISOString(),
  };

  return NextResponse.json({
    success: true,
    prospects: [mockNewProspect],
    message: "Scraper triggered successfully",
  });
}
