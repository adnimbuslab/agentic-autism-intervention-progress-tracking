"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useSchedules } from "@/lib/hooks/useSchedules";
import { useGoals } from "@/lib/hooks/useGoals";
import { useActors } from "@/lib/hooks/useActors";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { ScheduleForm } from "@/components/schedules/ScheduleForm";
import { OverdueIndicator } from "@/components/schedules/OverdueIndicator";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

export default function SchedulesPage() {
  const { childId } = useParams<{ childId: string }>();
  const { data: schedules, isLoading, error } = useSchedules(childId);
  const { data: goals } = useGoals(childId);
  const { data: actors } = useActors(childId);
  const [showForm, setShowForm] = useState(false);

  if (isLoading) return <LoadingState message="Loading schedules..." />;
  if (error) return <ErrorState error={error} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Observation Schedules</h2>
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? "Cancel" : "New Schedule"}
        </Button>
      </div>

      {showForm && (
        <ScheduleForm
          childId={childId}
          goals={goals}
          actors={actors}
          onSuccess={() => setShowForm(false)}
        />
      )}

      {!schedules?.length ? (
        <EmptyState
          title="No schedules"
          description="Create schedules to track observation frequency."
        />
      ) : (
        <div className="space-y-3">
          {schedules.map((schedule) => (
            <Card key={schedule.id}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">
                      Every {schedule.cadence_days} day
                      {schedule.cadence_days !== 1 ? "s" : ""}
                    </span>
                    <Badge
                      variant={schedule.is_active ? "success" : "neutral"}
                    >
                      {schedule.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </div>
                  {schedule.description && (
                    <p className="mt-1 text-sm text-gray-500">
                      {schedule.description}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-400">
                    {schedule.setting && (
                      <span>Setting: {schedule.setting}</span>
                    )}
                  </div>
                </div>
                <OverdueIndicator overdue={schedule.overdue} />
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
