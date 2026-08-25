"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { capitalize } from "@/lib/utils/formatters";
import { useRevokeActor } from "@/lib/hooks/useActors";
import type { ActorAssignment } from "@/lib/types";

interface ActorListProps {
  actors: ActorAssignment[];
  childId: string;
}

export function ActorList({ actors, childId }: ActorListProps) {
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);
  const revoke = useRevokeActor();

  async function handleRevoke() {
    if (!revokeTarget) return;
    await revoke.mutateAsync({ actorId: revokeTarget, childId });
    setRevokeTarget(null);
  }

  return (
    <>
      <div className="space-y-3">
        {actors.map((actor) => (
          <Card key={actor.id}>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {actor.invitation_email ?? actor.user_id}
                </p>
                <Badge variant="info" className="mt-1">
                  {capitalize(actor.role)}
                </Badge>
              </div>
              <Button
                variant="danger"
                size="sm"
                onClick={() => setRevokeTarget(actor.id)}
              >
                Revoke
              </Button>
            </div>
          </Card>
        ))}
      </div>

      <ConfirmDialog
        open={!!revokeTarget}
        onClose={() => setRevokeTarget(null)}
        onConfirm={handleRevoke}
        title="Revoke Access"
        message="This contributor will lose access to this child's data. This action cannot be undone."
        confirmLabel="Revoke"
        variant="danger"
        loading={revoke.isPending}
      />
    </>
  );
}
