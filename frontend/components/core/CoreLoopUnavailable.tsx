"use client";

/**
 * Shown when the Core Loop cannot load.
 *
 * Every Core Loop section is conditional on its data, so a failed fetch used
 * to render *nothing* - the dashboard silently fell back to looking exactly
 * like the previous version. A deploy would succeed, the new code would ship,
 * and the change would appear not to have happened.
 *
 * This makes the failure legible and names the most likely cause, including
 * the backend URL this build was compiled against.
 */
import { AlertTriangle, RefreshCw } from "lucide-react";
import { GlassCard } from "@/components/GlassCard";
import { ApiError, apiBaseUrl, isLocalApi } from "@/lib/api";

export default function CoreLoopUnavailable({
  error,
  onRetry,
}: {
  error: ApiError | null;
  onRetry: () => void;
}) {
  const notFound = error?.status === 404;
  const unreachable = error?.status === 0;

  let cause: string;
  if (isLocalApi) {
    cause =
      "This build points at a local backend, so it cannot work once deployed. " +
      "NEXT_PUBLIC_API_URL is baked in at build time - set it to your API's public " +
      "URL in the hosting dashboard and redeploy (changing it alone does nothing).";
  } else if (notFound) {
    cause =
      "The backend answered but does not have this endpoint, which means the API " +
      "is running an older build than the frontend. Redeploy the backend.";
  } else if (unreachable) {
    cause =
      "The backend could not be reached at all. Either it is asleep or down, or it " +
      "is rejecting this site's origin - add this domain to EXTRA_ORIGINS on the API " +
      "and restart it.";
  } else {
    cause = error?.message ?? "The backend returned an unexpected error.";
  }

  return (
    <GlassCard className="mb-5 border border-gold/30">
      <div className="flex items-start gap-3">
        <AlertTriangle size={17} className="text-gold mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white font-medium mb-1">
            Safe-to-Spend, Time Machine and Next Best Action couldn&apos;t load
          </p>
          <p className="text-sm text-mist leading-relaxed mb-3">{cause}</p>

          <div className="text-xs text-mist space-y-0.5 mb-3">
            <p>
              Calling: <code className="text-fog break-all">{apiBaseUrl}/api/dashboard/core</code>
            </p>
            {error && (
              <p>
                Response:{" "}
                <span className="text-fog">
                  {error.status === 0 ? "no response" : `HTTP ${error.status}`}
                </span>
                {error.requestId && <span className="text-mist"> · ref {error.requestId}</span>}
              </p>
            )}
          </div>

          <button
            onClick={onRetry}
            className="text-xs px-3 py-1.5 rounded-lg border border-line text-fog hover:text-white hover:border-mint/50 transition-colors inline-flex items-center gap-1.5"
          >
            <RefreshCw size={12} /> Try again
          </button>
        </div>
      </div>
    </GlassCard>
  );
}
