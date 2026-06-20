import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinMate — Your Financial Twin",
  description: "An agentic financial operating system that builds your financial digital twin and acts as your AI CFO.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-twin-glow bg-ink min-h-screen">
        <div className="flex">
          <Sidebar />
          <main className="flex-1 min-h-screen px-6 md:px-10 py-8 max-w-[1400px]">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
