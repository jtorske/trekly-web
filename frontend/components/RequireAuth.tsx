"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { nextQuery } from "@/lib/authLogic";

/**
 * Renders children only for a signed-in user. While the session is being
 * restored it shows `fallback` (never the protected content), then sends
 * signed-out visitors to sign in and back here afterwards.
 */
export default function RequireAuth({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const { status, sessionExpired } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (status !== "signedOut" && status !== "unconfigured") return;
    const search = searchParams.toString();
    const target = `${pathname}${search ? `?${search}` : ""}`;
    router.replace(`/login${nextQuery(target)}${sessionExpired ? "&expired=1" : ""}`);
  }, [status, sessionExpired, pathname, searchParams, router]);

  return status === "signedIn" ? <>{children}</> : <>{fallback}</>;
}
