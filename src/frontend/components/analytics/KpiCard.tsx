"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { capitalize, formatPercent } from "@/lib/utils/formatters";
import type { KpiResult } from "@/lib/types";

interface KpiCardProps {
  kpi: KpiResult;
}

export function KpiCard({ kpi }: KpiCardProps) {
  if (kpi.abstained) {
    return (
      <Card>
        <div className="flex items-start justify-between">
          <h4 className="text-sm font-medium text-gray-700">
            {capitalize(kpi.name)}
          </h4>
          <Badge variant="neutral">Withheld</Badge>
        </div>
        <p className="mt-2 text-xs text-gray-500">
          {kpi.abstention_reason ?? "Insufficient data for this metric."}
        </p>
      </Card>
    );
  }

  const displayValue =
    typeof kpi.value === "number" && kpi.value >= 0 && kpi.value <= 1
      ? formatPercent(kpi.value)
      : String(kpi.value ?? "—");

  return (
    <Card>
      <h4 className="text-sm font-medium text-gray-700">
        {capitalize(kpi.name)}
      </h4>
      <p className="mt-1 text-2xl font-semibold text-gray-900">
        {displayValue}
      </p>
      {kpi.denominator > 0 && (
        <p className="text-xs text-gray-400">
          {kpi.numerator} / {kpi.denominator}
        </p>
      )}
    </Card>
  );
}
