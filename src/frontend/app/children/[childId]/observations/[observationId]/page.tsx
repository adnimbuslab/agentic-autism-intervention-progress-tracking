"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useObservation } from "@/lib/hooks/useObservations";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { StructuredRecordView } from "@/components/records/StructuredRecordView";
import { formatDateTime, capitalize } from "@/lib/utils/formatters";

export default function ObservationDetailPage() {
  const { childId, observationId } = useParams<{
    childId: string;
    observationId: string;
  }>();
  const { data: obs, isLoading, error } = useObservation(observationId);

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  if (!obs) return <ErrorState error={{ message: "Observation not found" }} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Observation Detail</h2>
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

      {/* Source Evidence */}
      <Card title="Source Evidence — Original Observation">
        <p className="whitespace-pre-wrap text-sm text-gray-800">
          {obs.raw_text}
        </p>
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-400">
          <span>Setting: {capitalize(obs.setting)}</span>
          <span>Submitted: {formatDateTime(obs.submitted_at)}</span>
          <span>Observation ID: {obs.id}</span>
        </div>
      </Card>

      {/* Clarification Conversation */}
      {obs.clarification_turns && obs.clarification_turns.length > 0 && (
        <Card title="Source Evidence — Clarification Conversation">
          <div className="space-y-3">
            {obs.clarification_turns.map((turn, idx) => (
              <div key={idx} className="rounded-md bg-gray-50 p-3">
                <p className="text-xs font-medium text-blue-700 mb-1">
                  System Question:
                </p>
                <p className="text-sm text-gray-800">{turn.question}</p>
                <p className="mt-2 text-xs font-medium text-gray-600">
                  Response:
                </p>
                <p className="text-sm text-gray-800">
                  {turn.answer || "(No answer / Skipped)"}
                </p>
                <p className="mt-1 text-xs text-gray-400">
                  {formatDateTime(turn.created_at)}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* AI-Derived Structured Record */}
      {obs.structured_record && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-gray-500">
            AI-Derived Structured Information
          </h3>
          <StructuredRecordView record={obs.structured_record} />
          <div className="mt-2">
            <Link
              href={`/children/${childId}/records/${obs.structured_record.id}`}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              View full record details and version history
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
