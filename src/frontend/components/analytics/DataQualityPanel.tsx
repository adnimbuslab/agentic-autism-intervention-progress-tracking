"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { AnalyticsResponse } from "@/lib/types";

interface DataQualityPanelProps {
  analytics: AnalyticsResponse;
}

export function DataQualityPanel({ analytics }: DataQualityPanelProps) {
  return (
    <Card title="Data Quality Summary">
      <dl className="divide-y divide-gray-100 text-sm">
        <div className="flex justify-between py-2">
          <dt className="text-gray-600">KPIs Computed</dt>
          <dd className="font-medium text-gray-900">
            {analytics.kpis.filter((k) => !k.abstained).length} / {analytics.kpis.length}
          </dd>
        </div>
        <div className="flex justify-between py-2">
          <dt className="text-gray-600">Adequacy Level</dt>
          <dd>
            <Badge
              variant={
                analytics.adequacy.level === "ADEQUATE"
                  ? "success"
                  : analytics.adequacy.level === "LIMITED"
                    ? "warning"
                    : "error"
              }
            >
              {analytics.adequacy.level}
            </Badge>
          </dd>
        </div>
        <div className="flex justify-between py-2">
          <dt className="text-gray-600">Adequacy Checks Passed</dt>
          <dd className="font-medium text-gray-900">
            {analytics.adequacy.checks.filter((c) => c.passed).length} /{" "}
            {analytics.adequacy.checks.length}
          </dd>
        </div>
      </dl>

      {analytics.adequacy.quality_flags && analytics.adequacy.quality_flags.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-gray-500 mb-1">
            Quality Flags
          </p>
          <ul className="space-y-1">
            {analytics.adequacy.quality_flags.map((flag, i) => (
              <li key={i} className="text-xs text-yellow-700">
                {flag}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
