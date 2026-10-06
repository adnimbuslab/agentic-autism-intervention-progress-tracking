"use client";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { capitalize, formatDateTime } from "@/lib/utils/formatters";
import type { StructuredRecord } from "@/lib/types";

interface StructuredRecordViewProps {
  record: StructuredRecord;
}

// Only verified and corrected records are admitted to longitudinal
// analytics, so only those two read as settled. "Validated" means the
// deterministic engine found the record schema-conformant and nobody has
// looked at it yet, which is a waiting state, not a good one.
function statusVariant(status: string) {
  switch (status) {
    case "verified":
    case "corrected":
      return "success" as const;
    case "rejected":
      return "error" as const;
    default:
      return "warning" as const;
  }
}

export function StructuredRecordView({ record }: StructuredRecordViewProps) {
  const data = record.record_data;
  const fields = Object.entries(data).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-900">
            Structured Record
          </h3>
          <Badge variant="neutral">v{record.version}</Badge>
        </div>
        <Badge variant={statusVariant(record.status)}>
          {capitalize(record.status)}
        </Badge>
      </div>

      <p className="mb-1 text-xs text-gray-400">
        {record.status === "verified" || record.status === "corrected"
          ? "Reviewed by an interventionist — included in longitudinal analytics"
          : "AI-derived and unreviewed — excluded from longitudinal analytics until verified or corrected"}
      </p>

      <dl className="divide-y divide-gray-100">
        {fields.map(([key, value]) => (
          <div key={key} className="flex justify-between py-2 text-sm">
            <dt className="font-medium text-gray-600">{capitalize(key)}</dt>
            <dd className="text-gray-900">{String(value)}</dd>
          </div>
        ))}
      </dl>

      {record.validation_result && (
        <div className="mt-3 rounded-md bg-gray-50 p-3">
          <p className="text-xs font-medium text-gray-500 mb-1">
            Validation Result
          </p>
          <pre className="text-xs text-gray-600 overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(record.validation_result, null, 2)}
          </pre>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-400">
        <span>Provider: {record.provider}</span>
        <span>Model: {record.model}</span>
        <span>Prompt: {record.prompt_version}</span>
        <span>Created: {formatDateTime(record.created_at)}</span>
        {record.verified_by && (
          <span>Verified by: {record.verified_by}</span>
        )}
        {record.verified_at && (
          <span>Verified: {formatDateTime(record.verified_at)}</span>
        )}
        {record.corrected_by && (
          <span>Corrected by: {record.corrected_by}</span>
        )}
        {record.correction_reason && (
          <span>Reason: {record.correction_reason}</span>
        )}
      </div>
    </Card>
  );
}
