"use client";

import { Button } from "@/components/ui/Button";

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
}

function getMessage(error: unknown): string {
  if (error && typeof error === "object" && "message" in error) {
    return (error as { message: string }).message;
  }
  return "An unexpected error occurred.";
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16" role="alert">
      <p className="text-sm font-medium text-red-600">{getMessage(error)}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
