"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useReports, useGenerateReport } from "@/lib/hooks/useReports";
import { useReviewPeriods } from "@/lib/hooks/useReviewPeriods";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatDateTime } from "@/lib/utils/formatters";

function formatDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function ReportsPage() {
  const { childId } = useParams<{ childId: string }>();
  const { data: reports, isLoading, error } = useReports(childId);
  const generateReport = useGenerateReport();
  const [showGenerate, setShowGenerate] = useState(false);
  const [reviewPeriodId, setReviewPeriodId] = useState("");

  const {
    data: periods,
    isLoading: periodsLoading,
    error: periodsError,
  } = useReviewPeriods(childId);

  async function handleGenerate() {
    if (!reviewPeriodId) return;
    await generateReport.mutateAsync({
      childId,
      data: { review_period_id: reviewPeriodId },
    });
    setShowGenerate(false);
    setReviewPeriodId("");
  }

  if (isLoading) return <LoadingState message="Loading reports..." />;
  if (error) return <ErrorState error={error} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Reports</h2>
        <Button
          onClick={() => {
            setShowGenerate(!showGenerate);
            setReviewPeriodId("");
          }}
        >
          {showGenerate ? "Cancel" : "Generate Report"}
        </Button>
      </div>

      {showGenerate && (
        <Card title="Generate New Report">
          <p className="mb-3 text-xs text-gray-500">
            Reports are AI-generated drafts requiring interventionist review.
          </p>

          {periodsLoading && (
            <LoadingState message="Loading review periods..." />
          )}

          {periodsError && <ErrorState error={periodsError} />}

          {!periodsLoading && !periodsError && (!periods || periods.length === 0) && (
            <p className="text-sm text-gray-600" data-testid="no-periods-message">
              No review periods available. Create a review period in the{" "}
              <Link
                href={`/children/${childId}/analytics`}
                className="text-blue-600 underline hover:text-blue-800"
              >
                Analytics
              </Link>{" "}
              tab first.
            </p>
          )}

          {!periodsLoading && !periodsError && periods && periods.length > 0 && (
            <div className="space-y-3">
              <label className="block text-sm font-medium text-gray-700">
                Select a review period
              </label>
              <ul className="divide-y divide-gray-200 rounded border border-gray-200" role="list">
                {periods.map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => setReviewPeriodId(p.id)}
                      className={`w-full text-left px-4 py-3 transition-colors flex items-center justify-between ${
                        reviewPeriodId === p.id
                          ? "bg-blue-50 border-l-4 border-blue-500"
                          : "hover:bg-gray-50"
                      }`}
                      data-testid={`report-period-${p.id}`}
                    >
                      <span className="text-sm font-medium text-gray-900">
                        {formatDate(p.start_date)} &ndash; {formatDate(p.end_date)}
                      </span>
                      <span className="text-xs text-gray-500">
                        {p.is_active ? "Active" : "Inactive"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="flex justify-end">
                <Button
                  onClick={handleGenerate}
                  loading={generateReport.isPending}
                  disabled={!reviewPeriodId}
                >
                  Generate
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}

      {!reports?.length ? (
        <EmptyState
          title="No reports"
          description="Generate a report after collecting observations and computing analytics."
        />
      ) : (
        <div className="space-y-3">
          {reports.map((report) => (
            <Link
              key={report.id}
              href={`/children/${childId}/reports/${report.id}`}
            >
              <Card className="transition-shadow hover:shadow-md">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant="neutral">v{report.version}</Badge>
                    <Badge
                      variant={
                        report.validation_passed ? "success" : "error"
                      }
                    >
                      {report.validation_passed ? "Valid" : "Invalid"}
                    </Badge>
                    {report.flagged && (
                      <Badge variant="error">Flagged</Badge>
                    )}
                  </div>
                  <span className="text-xs text-gray-400">
                    {formatDateTime(report.generated_at)}
                  </span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
