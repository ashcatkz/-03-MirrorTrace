import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MirrorTrace — Prospection Automatisée",
  description: "Dashboard de prospection en temps réel pour les nouvelles immatriculations",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr" className="dark" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
