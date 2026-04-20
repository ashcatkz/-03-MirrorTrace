import { NextResponse } from "next/server";
import { MOCK_PROSPECTS } from "@/lib/mock-data";

export async function GET() {
  return NextResponse.json({ prospects: MOCK_PROSPECTS, total: MOCK_PROSPECTS.length });
}
