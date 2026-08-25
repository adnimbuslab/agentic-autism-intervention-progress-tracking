"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useActors } from "@/lib/hooks/useActors";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { ActorInviteForm } from "@/components/actors/ActorInviteForm";
import { ActorList } from "@/components/actors/ActorList";
import { Button } from "@/components/ui/Button";

export default function ActorsPage() {
  const { childId } = useParams<{ childId: string }>();
  const { data: actors, isLoading, error } = useActors(childId);
  const [showInvite, setShowInvite] = useState(false);

  if (isLoading) return <LoadingState message="Loading contributors..." />;
  if (error) return <ErrorState error={error} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Contributors</h2>
        <Button onClick={() => setShowInvite(!showInvite)}>
          {showInvite ? "Cancel" : "Invite Contributor"}
        </Button>
      </div>

      {showInvite && (
        <ActorInviteForm
          childId={childId}
          onSuccess={() => setShowInvite(false)}
        />
      )}

      {!actors?.length ? (
        <EmptyState
          title="No contributors"
          description="Invite contributors to submit observations for this child."
        />
      ) : (
        <ActorList actors={actors} childId={childId} />
      )}
    </div>
  );
}
