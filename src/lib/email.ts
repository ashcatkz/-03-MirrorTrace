import { Resend } from "resend";

const resend = new Resend(process.env.RESEND_API_KEY ?? "");

export function isResendConfigured() {
  return Boolean(process.env.RESEND_API_KEY);
}

export async function sendProspectEmail(prospect: {
  companyName: string;
  accountingNeed?: string;
  directorName?: string;
}): Promise<{ success: boolean; error?: string }> {
  if (!isResendConfigured()) {
    return { success: false, error: "RESEND_API_KEY not configured" };
  }

  const need = prospect.accountingNeed ?? "comptabilité et gestion fiscale";

  try {
    await resend.emails.send({
      from: "MirrorTrace <onboarding@resend.dev>",
      to: ["delivered@resend.dev"], // remplacer par l'email du prospect quand disponible
      subject: `Félicitations pour la création de ${prospect.companyName} 🎯`,
      text: `Bonjour,

J'ai vu que ${prospect.companyName} venait tout juste d'être immatriculée — félicitations pour le lancement.

On accompagne les nouvelles structures comme la vôtre sur la partie ${need} dès les premiers mois, pour partir sur de bonnes bases.

Je vous ai préparé une proposition adaptée à votre activité, je peux vous l'envoyer ?

Cordialement,
MirrorTrace`,
    });
    return { success: true };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { success: false, error: message };
  }
}
