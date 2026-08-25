"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useChild } from "@/lib/hooks/useChildren";
import { useObservations } from "@/lib/hooks/useObservations";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatDateTime, truncate, capitalize } from "@/lib/utils/formatters";

export default function ContributeHistoryPage() {
  const { childId } = useParams<{ childId: string }>();
  const { data: child } = useChild(childId);
  const { data: observations, isLoading, error } = useObservations(childId);

  if (isLoading) return <LoadingState message="Loading your observations..." />;
  if (error) return <ErrorState error={error} />;

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">My Observations</h1>
          {child && (
            <p className="text-sm text-gray-500">
              for {child.display_name}
            </p>
          )}
        </div>
        <Link href={`/contribute/${childId}/observe`}>
          <Button size="sm">New Observation</Button>
        </Link>
      </div>

      {!observations?.length ? (
        <EmptyState
          title="No observations yet"
          description="Submit your first observation to get started."
          actionLabel="New Observation"
          actionHref={`/contribute/${childId}/observe`}
        />
      ) : (
        <div className="space-y-3">
          {observations.map((obs) => (
            <Card key={obs.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-800">
                    {truncate(obs.raw_text, 160)}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-400">
                    <span>{formatDateTime(obs.submitted_at)}</span>
                    <span>{capitalize(obs.setting)}</span>
                  </div>
                </div>
                <Badge
                  variant={
                    obs.status === "finalized"
                      ? "success"
                      : obs.status === "failed"
                        ? "error"
                        : "warning"
                  }
                >
                  {capitalize(obs.status)}
                </Badge>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
