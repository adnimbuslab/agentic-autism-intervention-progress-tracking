"use client";

import { useParams } from "next/navigation";
import { useAuditTrail } from "@/lib/hooks/useAudit";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { formatDateTime } from "@/lib/utils/formatters";

export default function AuditPage() {
  const { childId } = useParams<{ childId: string }>();
  const { data: events, isLoading, error } = useAuditTrail(childId);

  if (isLoading) return <LoadingState message="Loading audit trail..." />;
  if (error) return <ErrorState error={error} />;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Audit Trail</h2>

      {!events?.length ? (
        <EmptyState
          title="No audit events"
          description="Audit events are recorded as actions are taken."
        />
      ) : (
        <Card>
          <div className="divide-y divide-gray-100">
            {events.map((event) => (
              <div key={event.id} className="py-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant="info">{event.action}</Badge>
                    <span className="text-sm text-gray-800">
                      {event.resource_type}
                    </span>
                  </div>
                  <span className="text-xs text-gray-400">
                    {formatDateTime(event.created_at)}
                  </span>
                </div>
                {event.detail && (
                  <pre className="mt-1 text-xs text-gray-500 overflow-x-auto">
                    {typeof event.detail === "string"
                      ? event.detail
                      : JSON.stringify(event.detail, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
