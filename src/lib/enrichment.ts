export async function enrichDirector(siren: string): Promise<string> {
  if (!siren || siren.length < 9) return "Non communiqué";

  try {
    const url = `https://recherche-entreprises.api.gouv.fr/search?q=${siren}&per_page=1`;
    const resp = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(4000),
    });
    if (!resp.ok) return "Non communiqué";

    const data = await resp.json();
    const company = data.results?.[0];
    if (!company) return "Non communiqué";

    const dirigeants: Array<{ nom?: string; prenoms?: string; nom_complet?: string }> =
      company.dirigeants ?? [];

    const first = dirigeants[0];
    if (!first) return "Non communiqué";

    if (first.nom_complet) return first.nom_complet;
    if (first.nom && first.prenoms) return `${first.prenoms} ${first.nom}`;
    if (first.nom) return first.nom;

    return "Non communiqué";
  } catch {
    return "Non communiqué";
  }
}
