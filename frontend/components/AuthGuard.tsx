"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { getToken } from "@/lib/api";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  const PUBLIC = ["/login", "/welcome"];
  const isPublic = PUBLIC.includes(pathname);

  useEffect(() => {
    const token = getToken();
    if (!token && !isPublic) {
      router.replace("/welcome");
      return;
    }
    if (token && isPublic) {
      router.replace("/");
      return;
    }
    setReady(true);
  }, [pathname, isPublic, router]);

  // Public pages render standalone (no app shell).
  if (isPublic) return <>{children}</>;

  if (!ready) {
    return <div className="min-h-screen flex items-center justify-center text-mist">Loading…</div>;
  }

  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1 min-h-screen px-6 md:px-10 pt-20 md:pt-8 pb-8 max-w-[1400px]">{children}</main>
    </div>
  );
}
