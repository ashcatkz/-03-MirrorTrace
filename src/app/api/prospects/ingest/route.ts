import { NextRequest, NextResponse } from "next/server";
import { Prospect } from "@/types/prospect";

const SCRAPER_SECRET = process.env.SCRAPER_SECRET ?? "";

export async function POST(req: NextRequest) {
  const secret = req.headers.get("x-scraper-secret") ?? "";
  if (SCRAPER_SECRET && secret !== SCRAPER_SECRET) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const prospects: Prospect[] = body.prospects ?? [];

  if (!Array.isArray(prospects) || prospects.length === 0) {
    return NextResponse.json({ error: "No prospects provided" }, { status: 400 });
  }

  // In production: persist to DB (Prisma/Supabase/PlanetScale)
  // Here we just validate and return
  const validated = prospects.filter(
    (p) => p.siret && p.companyName && p.nafCode
  );

  console.log(`[Ingest] Received ${validated.length} new prospects`);

  return NextResponse.json({
    success: true,
    ingested: validated.length,
    timestamp: new Date().toISOString(),
  });
}
