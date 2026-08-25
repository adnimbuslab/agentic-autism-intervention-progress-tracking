"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { formatDateTime, truncate, capitalize } from "@/lib/utils/formatters";
import type { Observation } from "@/lib/types";

interface ObservationCardProps {
  observation: Observation;
  childId: string;
  basePath?: string;
}

function statusVariant(status: string) {
  switch (status) {
    case "finalized":
      return "success" as const;
    case "failed":
      return "error" as const;
    case "clarifying":
      return "warning" as const;
    default:
      return "info" as const;
  }
}

export function ObservationCard({
  observation,
  childId,
  basePath = `/children/${childId}/observations`,
}: ObservationCardProps) {
  return (
    <Link href={`${basePath}/${observation.id}`}>
      <Card className="transition-shadow hover:shadow-md">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm text-gray-800">
              {truncate(observation.raw_text, 160)}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-400">
              <span>{formatDateTime(observation.submitted_at)}</span>
              <span>{capitalize(observation.setting)}</span>
            </div>
          </div>
          <Badge variant={statusVariant(observation.status)}>
            {capitalize(observation.status)}
          </Badge>
        </div>
      </Card>
    </Link>
  );
}
