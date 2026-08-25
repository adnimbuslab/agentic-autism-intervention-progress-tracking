"use client";

import { useParams } from "next/navigation";
import { useObservations } from "@/lib/hooks/useObservations";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { ObservationCard } from "@/components/observations/ObservationCard";

export default function ObservationsPage() {
  const { childId } = useParams<{ childId: string }>();
  const { data: observations, isLoading, error } = useObservations(childId);

  if (isLoading) return <LoadingState message="Loading observations..." />;
  if (error) return <ErrorState error={error} />;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Observations</h2>

      {!observations?.length ? (
        <EmptyState
          title="No observations"
          description="No observations have been submitted for this child yet."
        />
      ) : (
        <div className="space-y-3">
          {observations.map((obs) => (
            <ObservationCard
              key={obs.id}
              observation={obs}
              childId={childId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
