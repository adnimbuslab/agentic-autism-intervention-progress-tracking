"use client";

import { Badge } from "@/components/ui/Badge";
import type { AdequacyResponse } from "@/lib/types";

interface AdequacyBannerProps {
  adequacy: AdequacyResponse;
}

function levelVariant(level: string) {
  switch (level) {
    case "ADEQUATE":
      return "success" as const;
    case "LIMITED":
      return "warning" as const;
    case "INSUFFICIENT":
      return "error" as const;
    default:
      return "neutral" as const;
  }
}

export function AdequacyBanner({ adequacy }: AdequacyBannerProps) {
  const failedChecks = adequacy.checks.filter((c) => !c.passed);

  return (
    <div
      className={`rounded-lg border p-4 ${
        adequacy.level === "ADEQUATE"
          ? "border-green-200 bg-green-50"
          : adequacy.level === "LIMITED"
            ? "border-yellow-200 bg-yellow-50"
            : "border-red-200 bg-red-50"
      }`}
      role="status"
    >
      <div className="flex items-center gap-2">
        <Badge variant={levelVariant(adequacy.level)}>
          {adequacy.level}
        </Badge>
        <span className="text-sm font-medium text-gray-900">
          Data Adequacy Assessment
        </span>
      </div>

      {adequacy.level !== "ADEQUATE" && failedChecks.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-gray-600 mb-1">
            Evidence Limitations:
          </p>
          <ul className="list-disc pl-5 space-y-1">
            {failedChecks.map((check) => (
              <li key={check.check} className="text-xs text-gray-600">
                <span className="font-medium">{check.check}:</span>{" "}
                {check.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      {adequacy.level === "INSUFFICIENT" && (
        <p className="mt-2 text-xs text-red-700">
          Analytics are withheld because the available evidence does not meet
          minimum adequacy requirements.
        </p>
      )}
    </div>
  );
}
