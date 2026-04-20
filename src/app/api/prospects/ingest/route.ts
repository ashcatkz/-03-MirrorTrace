import { NextRequest, NextResponse } from "next/server";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";
import { sendProspectEmail, isResendConfigured } from "@/lib/email";
import { enrichDirector } from "@/lib/enrichment";
import { Prospect } from "@/types/prospect";

const SCRAPER_SECRET = process.env.SCRAPER_SECRET ?? "";

// Fallback mémoire si Supabase non configuré
const memoryStore: Prospect[] = [];

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

  const validated = prospects.filter((p) => p.siret && p.companyName);
  let ingested = 0;

  for (const prospect of validated) {
    // 1. Enrichissement dirigeant
    if (!prospect.directorName || prospect.directorName === "Non communiqué") {
      prospect.directorName = await enrichDirector(prospect.siren);
    }

    if (isSupabaseConfigured()) {
      // 2a. Upsert Supabase (ignore doublons par siret)
      const { error } = await supabase.from("prospects").upsert(
        {
          id: prospect.id,
          siret: prospect.siret,
          siren: prospect.siren,
          company_name: prospect.companyName,
          director_name: prospect.directorName,
          naf_code: prospect.nafCode,
          naf_label: prospect.nafLabel,
          created_at: prospect.createdAt,
          address: prospect.address,
          city: prospect.city,
          postal_code: prospect.postalCode,
          email: prospect.email ?? null,
          phone: prospect.phone ?? null,
          status: prospect.status ?? "identified",
          ai_insight: prospect.aiInsight ?? null,
          accounting_need: prospect.accountingNeed ?? null,
          estimated_revenue: prospect.estimatedRevenue ?? null,
          invoice_generated: prospect.invoiceGenerated ?? false,
          scraped_at: prospect.scrapedAt,
        },
        { onConflict: "siret", ignoreDuplicates: true }
      );

      if (error) {
        console.error(`[Ingest] Supabase error for ${prospect.siret}:`, error.message);
        continue;
      }
      ingested++;
    } else {
      // 2b. Fallback mémoire
      const exists = memoryStore.some((p) => p.siret === prospect.siret);
      if (!exists) {
        memoryStore.unshift(prospect);
        if (memoryStore.length > 500) memoryStore.splice(500);
        ingested++;
      }
    }

    // 3. Email automatique
    if (isResendConfigured()) {
      const emailResult = await sendProspectEmail(prospect);

      if (emailResult.success && isSupabaseConfigured()) {
        // Log dans emails_sent
        await supabase.from("emails_sent").insert({
          prospect_id: prospect.id,
          siret: prospect.siret,
          company_name: prospect.companyName,
        });

        // Mettre à jour statut → email_sent
        await supabase
          .from("prospects")
          .update({ status: "email_sent" })
          .eq("siret", prospect.siret);
      }

      if (emailResult.error) {
        console.warn(`[Email] ${prospect.companyName}: ${emailResult.error}`);
      }
    }
  }

  console.log(`[Ingest] +${ingested}/${validated.length} | Supabase: ${isSupabaseConfigured()} | Email: ${isResendConfigured()}`);

  return NextResponse.json({
    success: true,
    ingested,
    timestamp: new Date().toISOString(),
  });
}

export async function GET() {
  if (isSupabaseConfigured()) {
    const { data, error } = await supabase
      .from("prospects")
      .select("*")
      .order("scraped_at", { ascending: false })
      .limit(500);

    if (error) {
      console.error("[Ingest GET] Supabase error:", error.message);
      return NextResponse.json({ prospects: [] });
    }

    // Remap snake_case → camelCase pour le frontend
    const mapped: Prospect[] = (data ?? []).map((row) => ({
      id: row.id,
      siret: row.siret,
      siren: row.siren,
      companyName: row.company_name,
      directorName: row.director_name,
      nafCode: row.naf_code,
      nafLabel: row.naf_label,
      createdAt: row.created_at,
      address: row.address,
      city: row.city,
      postalCode: row.postal_code,
      email: row.email,
      phone: row.phone,
      status: row.status,
      aiInsight: row.ai_insight,
      accountingNeed: row.accounting_need,
      estimatedRevenue: row.estimated_revenue,
      invoiceGenerated: row.invoice_generated,
      scrapedAt: row.scraped_at,
    }));

    return NextResponse.json({ prospects: mapped });
  }

  // Fallback mémoire
  return NextResponse.json({ prospects: memoryStore });
}
