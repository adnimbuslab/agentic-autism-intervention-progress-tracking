"use client";

import Link from "next/link";
import { useChildren } from "@/lib/hooks/useChildren";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { Card } from "@/components/ui/Card";

export default function ContributeHomePage() {
  const { data: children, isLoading, error } = useChildren();

  if (isLoading) return <LoadingState message="Loading your children..." />;
  if (error) return <ErrorState error={error} />;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Your Children</h1>
      <p className="text-sm text-gray-500">
        Select a child to submit an observation or view your history.
      </p>

      {!children?.length ? (
        <EmptyState
          title="No children assigned"
          description="You haven't been assigned to any children yet. Contact your interventionist for access."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {children.map((child) => (
            <Card key={child.id} className="space-y-3">
              <h3 className="font-medium text-gray-900">
                {child.display_name}
              </h3>
              <div className="flex gap-2">
                <Link
                  href={`/contribute/${child.id}/observe`}
                  className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
                >
                  New Observation
                </Link>
                <Link
                  href={`/contribute/${child.id}/history`}
                  className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  My History
                </Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
