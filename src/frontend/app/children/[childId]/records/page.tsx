"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useRecords } from "@/lib/hooks/useRecords";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { capitalize, formatDateTime } from "@/lib/utils/formatters";

export default function RecordsPage() {
  const { childId } = useParams<{ childId: string }>();
  const { data: records, isLoading, error } = useRecords(childId);

  if (isLoading) return <LoadingState message="Loading records..." />;
  if (error) return <ErrorState error={error} />;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Structured Records</h2>

      {!records?.length ? (
        <EmptyState
          title="No records"
          description="Structured records are created after observations are processed."
        />
      ) : (
        <div className="space-y-3">
          {records.map((record) => (
            <Link
              key={record.id}
              href={`/children/${childId}/records/${record.id}`}
            >
              <Card className="transition-shadow hover:shadow-md">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="neutral">v{record.version}</Badge>
                      <Badge
                        variant={
                          record.status === "validated"
                            ? "success"
                            : record.status === "rejected"
                              ? "error"
                              : "warning"
                        }
                      >
                        {capitalize(record.status)}
                      </Badge>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-400">
                      <span>Provider: {record.provider}</span>
                      <span>{formatDateTime(record.created_at)}</span>
                    </div>
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
