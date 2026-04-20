import { NextResponse } from "next/server";

export async function POST() {
  // The Python scraper runs independently and POSTs to /api/prospects/ingest
  // This endpoint just confirms the scraper is managed externally
  return NextResponse.json({
    success: true,
    prospects: [],
    message: "Scraper runs independently — check terminal for status",
  });
}
