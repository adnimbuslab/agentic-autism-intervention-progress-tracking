"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useVerifyRecord } from "@/lib/hooks/useRecords";
import type { StructuredRecord } from "@/lib/types";

interface VerificationPanelProps {
  record: StructuredRecord;
  onCorrect: () => void;
}

/**
 * The human gate in front of longitudinal analytics.
 *
 * Deterministic validation establishes that a record is schema-conformant,
 * not that it reads the observation correctly, so a validated record is
 * withheld from analytics until an interventionist either accepts it as
 * written (verify) or rewrites it (correct). A record the adequacy router
 * sent for review cannot be accepted as written at all — accepting one
 * would silently undo the abstention — so only correction is offered there.
 */
export function VerificationPanel({
  record,
  onCorrect,
}: VerificationPanelProps) {
  const [error, setError] = useState("");
  const verifyRecord = useVerifyRecord();

  if (record.status === "verified" || record.status === "corrected") {
    return null;
  }

  const acceptable = record.status === "validated";

  async function handleVerify() {
    setError("");
    try {
      await verifyRecord.mutateAsync({ recordId: record.id });
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Verification failed. The record may have changed state.",
      );
    }
  }

  return (
    <Card title="Review required">
      <p className="mb-3 text-xs text-gray-500">
        {acceptable
          ? "This record is excluded from longitudinal analytics until you accept it as written or correct it."
          : "This record was routed for review because the evidence was inadequate. It cannot be accepted as written — correct it or leave it out."}
      </p>
      {error && (
        <p className="mb-3 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={onCorrect}>
          Correct
        </Button>
        {acceptable && (
          <Button
            size="sm"
            onClick={handleVerify}
            loading={verifyRecord.isPending}
          >
            Verify as written
          </Button>
        )}
      </div>
    </Card>
  );
}
