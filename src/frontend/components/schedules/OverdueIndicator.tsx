"use client";

import { Badge } from "@/components/ui/Badge";
import type { OverdueInfo } from "@/lib/types";

interface OverdueIndicatorProps {
  overdue: OverdueInfo | null;
}

export function OverdueIndicator({ overdue }: OverdueIndicatorProps) {
  if (!overdue || !overdue.is_overdue) {
    return <Badge variant="success">On Track</Badge>;
  }

  return (
    <Badge variant="error">
      Overdue by {overdue.days_overdue} day{overdue.days_overdue !== 1 ? "s" : ""}
    </Badge>
  );
}
