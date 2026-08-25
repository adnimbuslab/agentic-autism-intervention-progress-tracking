"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useReports, useGenerateReport } from "@/lib/hooks/useReports";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { formatDateTime } from "@/lib/utils/formatters";

export default function ReportsPage() {
  const { childId } = useParams<{ childId: string }>();
  const { data: reports, isLoading, error } = useReports(childId);
  const generateReport = useGenerateReport();
  const [showGenerate, setShowGenerate] = useState(false);
  const [reviewPeriodId, setReviewPeriodId] = useState("");

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
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
        <Button onClick={() => setShowGenerate(!showGenerate)}>
          {showGenerate ? "Cancel" : "Generate Report"}
        </Button>
      </div>

      {showGenerate && (
        <Card title="Generate New Report">
          <p className="mb-3 text-xs text-gray-500">
            Reports are AI-generated drafts requiring interventionist review.
          </p>
          <form onSubmit={handleGenerate} className="space-y-4">
            <Input
              label="Review Period ID"
              value={reviewPeriodId}
              onChange={(e) => setReviewPeriodId(e.target.value)}
              placeholder="Enter review period ID"
              required
            />
            <div className="flex justify-end">
              <Button type="submit" loading={generateReport.isPending}>
                Generate
              </Button>
            </div>
          </form>
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
