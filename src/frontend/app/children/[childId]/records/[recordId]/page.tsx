"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useRecord, useRecordVersions } from "@/lib/hooks/useRecords";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { StructuredRecordView } from "@/components/records/StructuredRecordView";
import { CorrectionForm } from "@/components/records/CorrectionForm";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatDateTime } from "@/lib/utils/formatters";

export default function RecordDetailPage() {
  const { recordId } = useParams<{ childId: string; recordId: string }>();
  const { data: record, isLoading, error } = useRecord(recordId);
  const { data: versions } = useRecordVersions(recordId);
  const [showCorrection, setShowCorrection] = useState(false);

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  if (!record) return <ErrorState error={{ message: "Record not found" }} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Record Detail</h2>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setShowCorrection(!showCorrection)}
        >
          {showCorrection ? "Cancel" : "Submit Correction"}
        </Button>
      </div>

      <StructuredRecordView record={record} />

      {showCorrection && (
        <CorrectionForm
          record={record}
          onSuccess={() => setShowCorrection(false)}
        />
      )}

      {/* Version History */}
      {versions && versions.length > 1 && (
        <Card title="Version History">
          <p className="mb-2 text-xs text-gray-500">
            Corrections create new versions. Originals are never overwritten.
          </p>
          <div className="divide-y divide-gray-100">
            {versions.map((v) => (
              <div
                key={`${v.id}-v${v.version}`}
                className="flex items-center justify-between py-2"
              >
                <div className="flex items-center gap-2">
                  <Badge variant="neutral">v{v.version}</Badge>
                  <span className="text-sm text-gray-600">
                    {formatDateTime(v.created_at)}
                  </span>
                </div>
                {v.correction_reason && (
                  <span className="text-xs text-gray-400">
                    {v.correction_reason}
                  </span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
