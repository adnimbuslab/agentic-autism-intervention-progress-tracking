"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useReport, useEvidencePacket } from "@/lib/hooks/useReports";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { ReportViewer } from "@/components/reports/ReportViewer";
import { FlagButton } from "@/components/reports/FlagButton";
import { Card } from "@/components/ui/Card";
import { capitalize } from "@/lib/utils/formatters";

export default function ReportDetailPage() {
  const { childId, reportId } = useParams<{
    childId: string;
    reportId: string;
  }>();
  const { data: report, isLoading, error } = useReport(reportId);
  const { data: evidence } = useEvidencePacket(reportId);

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  if (!report) return <ErrorState error={{ message: "Report not found" }} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Report Detail</h2>
        <FlagButton reportId={reportId} isFlagged={report.flagged} />
      </div>

      <ReportViewer report={report} />

      {/* Evidence Packet */}
      {evidence && (
        <Card title="Evidence Packet">
          <p className="mb-2 text-xs text-gray-500">
            The factual source data used to generate this report.
          </p>
          <dl className="divide-y divide-gray-100 text-sm">
            <div className="flex justify-between py-2">
              <dt className="text-gray-600">Review Period</dt>
              <dd className="text-gray-900">
                {evidence.review_period_start} — {evidence.review_period_end}
              </dd>
            </div>
            <div className="flex justify-between py-2">
              <dt className="text-gray-600">Observations</dt>
              <dd className="text-gray-900">{evidence.observation_count}</dd>
            </div>
            <div className="flex justify-between py-2">
              <dt className="text-gray-600">Abstained Records</dt>
              <dd className="text-gray-900">{evidence.abstained_count}</dd>
            </div>
            <div className="flex justify-between py-2">
              <dt className="text-gray-600">Records for Review</dt>
              <dd className="text-gray-900">{evidence.review_count}</dd>
            </div>
          </dl>

          {/* Contributor representation */}
          {Object.keys(evidence.contributor_summary).length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium text-gray-500 mb-1">
                Contributor Representation
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(evidence.contributor_summary).map(
                  ([role, count]) => (
                    <span
                      key={role}
                      className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-600"
                    >
                      {capitalize(role)}: {count as number}
                    </span>
                  ),
                )}
              </div>
            </div>
          )}

          {/* Setting representation */}
          {Object.keys(evidence.setting_summary).length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium text-gray-500 mb-1">
                Setting Representation
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(evidence.setting_summary).map(
                  ([setting, count]) => (
                    <span
                      key={setting}
                      className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-600"
                    >
                      {capitalize(setting)}: {count as number}
                    </span>
                  ),
                )}
              </div>
            </div>
          )}

          {/* Evidence traceability */}
          {evidence.record_ids.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium text-gray-500 mb-1">
                Source Records ({evidence.record_ids.length})
              </p>
              <div className="space-y-1">
                {evidence.record_ids.slice(0, 10).map((rid) => (
                  <Link
                    key={rid}
                    href={`/children/${childId}/records/${rid}`}
                    className="block text-xs text-blue-600 hover:text-blue-800 font-mono"
                  >
                    {rid}
                  </Link>
                ))}
                {evidence.record_ids.length > 10 && (
                  <p className="text-xs text-gray-400">
                    +{evidence.record_ids.length - 10} more
                  </p>
                )}
              </div>
            </div>
          )}

          {evidence.quality_flags.length > 0 && (
            <div className="mt-3">
              <p className="text-xs font-medium text-gray-500 mb-1">
                Quality Flags
              </p>
              <ul className="space-y-1">
                {evidence.quality_flags.map((flag, i) => (
                  <li key={i} className="text-xs text-yellow-700">
                    {flag}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
