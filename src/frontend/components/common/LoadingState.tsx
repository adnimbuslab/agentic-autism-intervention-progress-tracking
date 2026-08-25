"use client";

import { Spinner } from "@/components/ui/Spinner";

interface LoadingStateProps {
  message?: string;
}

export function LoadingState({ message = "Loading..." }: LoadingStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16" role="status">
      <Spinner size="lg" />
      <p className="mt-3 text-sm text-gray-500">{message}</p>
    </div>
  );
}
