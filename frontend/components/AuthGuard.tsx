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
    // overflow-x-hidden + min-w-0 together stop a wide child (a transaction
    // table, a chart) from stretching the flex row past the viewport. Without
    // min-w-0 a flex item refuses to shrink below its content, which pushed
    // the page sideways on mobile and dragged the fixed header out of line.
    <div className="flex w-full overflow-x-hidden">
      <Sidebar />
      <main className="flex-1 min-w-0 min-h-screen w-full px-4 sm:px-6 md:px-10 pt-[4.5rem] md:pt-8 pb-12">
        <div className="max-w-[1400px] mx-auto">{children}</div>
      </main>
    </div>
  );
}
