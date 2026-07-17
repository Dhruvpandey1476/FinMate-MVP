import type { Metadata } from "next";
import AuthGuard from "@/components/AuthGuard";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinMate — Your Financial Twin",
  description: "An agentic financial operating system that builds your financial digital twin and acts as your AI CFO.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-twin-glow bg-ink min-h-screen">
        <AuthGuard>{children}</AuthGuard>
      </body>
    </html>
  );
}
