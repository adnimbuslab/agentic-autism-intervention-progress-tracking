"use client";

import { useParams, useRouter } from "next/navigation";
import { useChild } from "@/lib/hooks/useChildren";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { ConversationalCapture } from "@/components/observations/ConversationalCapture";

export default function ContributeObservePage() {
  const { childId } = useParams<{ childId: string }>();
  const { data: child, isLoading, error } = useChild(childId);
  const router = useRouter();

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  if (!child) return <ErrorState error={{ message: "Child not found" }} />;

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Submit Observation</h1>
        <p className="text-sm text-gray-500">
          for {child.display_name}
        </p>
      </div>

      <ConversationalCapture
        childId={childId}
        onComplete={() => router.push(`/contribute/${childId}/history`)}
      />
    </div>
  );
}
