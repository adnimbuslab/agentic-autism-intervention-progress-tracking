"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useAnalytics } from "@/lib/hooks/useAnalytics";
import {
  useReviewPeriods,
  useCreateReviewPeriod,
} from "@/lib/hooks/useReviewPeriods";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { AdequacyBanner } from "@/components/analytics/AdequacyBanner";
import { KpiCard } from "@/components/analytics/KpiCard";
import { DataQualityPanel } from "@/components/analytics/DataQualityPanel";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

function formatDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function AnalyticsPage() {
  const { childId } = useParams<{ childId: string }>();
  const [reviewPeriodId, setReviewPeriodId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  const {
    data: periods,
    isLoading: periodsLoading,
    error: periodsError,
  } = useReviewPeriods(childId);
  const createPeriod = useCreateReviewPeriod();

  const {
    data: analytics,
    isLoading,
    error,
  } = useAnalytics(childId, reviewPeriodId);

  async function handleCreatePeriod(e: React.FormEvent) {
    e.preventDefault();
    const result = await createPeriod.mutateAsync({
      childId,
      data: { start_date: startDate, end_date: endDate },
    });
    setReviewPeriodId(result.id);
    setShowCreate(false);
    setStartDate("");
    setEndDate("");
  }

  if (!reviewPeriodId) {
    return (
      <div className="space-y-6">
        <h2 className="text-xl font-semibold">Analytics</h2>

        {periodsLoading && <LoadingState message="Loading review periods..." />}
        {periodsError && <ErrorState error={periodsError} />}

        {!periodsLoading && !periodsError && periods && periods.length > 0 && (
          <Card title="Select a Review Period">
            <ul className="divide-y divide-gray-200" role="list">
              {periods.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => setReviewPeriodId(p.id)}
                    className="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors flex items-center justify-between"
                    data-testid={`period-${p.id}`}
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
          </Card>
        )}

        {!periodsLoading &&
          !periodsError &&
          (!periods || periods.length === 0) &&
          !showCreate && (
            <EmptyState
              title="No review periods"
              description="Create a review period to define the time window for analysis."
              actionLabel="Create Review Period"
              onAction={() => setShowCreate(true)}
            />
          )}

        {!showCreate && periods && periods.length > 0 && (
          <div className="flex justify-end">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowCreate(true)}
            >
              Create New Period
            </Button>
          </div>
        )}

        {showCreate && (
          <Card title="Create Review Period">
            <form onSubmit={handleCreatePeriod} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Input
                  label="Start Date"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  required
                />
                <Input
                  label="End Date"
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  required
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button
                  variant="ghost"
                  onClick={() => setShowCreate(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" loading={createPeriod.isPending}>
                  Create &amp; Compute
                </Button>
              </div>
            </form>
          </Card>
        )}
      </div>
    );
  }

  if (isLoading) return <LoadingState message="Computing analytics..." />;
  if (error) return <ErrorState error={error} />;
  if (!analytics)
    return <ErrorState error={{ message: "No analytics available" }} />;

  const isInsufficient = analytics.adequacy.level === "INSUFFICIENT";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Analytics</h2>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setReviewPeriodId("")}
        >
          Change Period
        </Button>
      </div>

      <AdequacyBanner adequacy={analytics.adequacy} />

      {isInsufficient ? (
        <Card>
          <p className="text-sm text-gray-600">
            Analytics are withheld because the available evidence does not meet
            minimum adequacy requirements. Collect more observations across
            different settings and contributors to enable analysis.
          </p>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {analytics.kpis.map((kpi) => (
              <KpiCard key={kpi.name} kpi={kpi} />
            ))}
          </div>
          <DataQualityPanel analytics={analytics} />
        </>
      )}
    </div>
  );
}
