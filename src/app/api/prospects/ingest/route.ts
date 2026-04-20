import { NextRequest, NextResponse } from "next/server";

const SCRAPER_SECRET = process.env.SCRAPER_SECRET ?? "";

// Stockage en mémoire (remplacer par DB en production)
const ingestedProspects: unknown[] = [];

export async function POST(req: NextRequest) {
  const secret = req.headers.get("x-scraper-secret") ?? "";
  if (SCRAPER_SECRET && secret !== SCRAPER_SECRET) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const prospects = body.prospects ?? [];

  if (!Array.isArray(prospects) || prospects.length === 0) {
    return NextResponse.json({ error: "No prospects provided" }, { status: 400 });
  }

  const validated = prospects.filter((p: any) => p.siret && p.companyName);
  ingestedProspects.unshift(...validated);

  // Garder seulement les 500 derniers en mémoire
  if (ingestedProspects.length > 500) ingestedProspects.splice(500);

  console.log(`[Ingest] +${validated.length} prospects | Total: ${ingestedProspects.length}`);

  return NextResponse.json({
    success: true,
    ingested: validated.length,
    timestamp: new Date().toISOString(),
  });
}

export async function GET() {
  return NextResponse.json({ prospects: ingestedProspects });
}
