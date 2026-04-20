import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export async function POST(req: NextRequest) {
  if (!process.env.OPENAI_API_KEY) {
    return NextResponse.json(
      { error: "OPENAI_API_KEY not configured" },
      { status: 503 }
    );
  }

  const { companyName, nafCode, nafLabel, city, legalForm } = await req.json();

  if (!companyName || !nafCode) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const prompt = `Tu es un expert-comptable spécialisé dans la prospection commerciale.
Analyse cette nouvelle entreprise et génère une proposition commerciale concise.

Entreprise : ${companyName}
Forme juridique : ${legalForm ?? "Non précisée"}
Code NAF : ${nafCode} — ${nafLabel ?? ""}
Ville : ${city ?? "France"}

Réponds UNIQUEMENT en JSON avec ces 3 champs :
- aiInsight : phrase d'accroche sur les besoins probables (max 120 caractères)
- accountingNeed : mission comptable recommandée (max 150 caractères)
- estimatedRevenue : tarif mensuel estimé en EUR (entier entre 800 et 5000)`;

  const response = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: prompt }],
    response_format: { type: "json_object" },
    max_tokens: 200,
    temperature: 0.7,
  });

  const content = response.choices[0].message.content ?? "{}";

  try {
    const parsed = JSON.parse(content);
    return NextResponse.json(parsed);
  } catch {
    return NextResponse.json(
      { error: "Failed to parse AI response" },
      { status: 500 }
    );
  }
}
