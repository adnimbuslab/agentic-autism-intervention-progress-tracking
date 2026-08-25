"use client";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { capitalize, formatDate } from "@/lib/utils/formatters";
import type { Goal } from "@/lib/types";

interface GoalCardProps {
  goal: Goal;
}

export function GoalCard({ goal }: GoalCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-medium text-gray-900">{goal.title}</h3>
          {goal.description && (
            <p className="mt-1 text-sm text-gray-500">{goal.description}</p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge variant="info">{capitalize(goal.domain)}</Badge>
            <Badge variant="neutral">{capitalize(goal.goal_type)}</Badge>
            {goal.target_date && (
              <span className="text-xs text-gray-400">
                Target: {formatDate(goal.target_date)}
              </span>
            )}
          </div>
        </div>
        <Badge variant={goal.is_active ? "success" : "neutral"}>
          {goal.is_active ? "Active" : "Inactive"}
        </Badge>
      </div>
    </Card>
  );
}
