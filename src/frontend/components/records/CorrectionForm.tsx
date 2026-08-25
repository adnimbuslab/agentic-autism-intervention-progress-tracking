"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { Card } from "@/components/ui/Card";
import { useCorrectRecord } from "@/lib/hooks/useRecords";
import type { StructuredRecord } from "@/lib/types";

interface CorrectionFormProps {
  record: StructuredRecord;
  onSuccess?: () => void;
}

export function CorrectionForm({ record, onSuccess }: CorrectionFormProps) {
  const [editedData, setEditedData] = useState(
    JSON.stringify(record.record_data, null, 2),
  );
  const [reason, setReason] = useState("");
  const [parseError, setParseError] = useState("");
  const correctRecord = useCorrectRecord();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setParseError("");

    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(editedData);
    } catch {
      setParseError("Invalid JSON. Please fix the syntax.");
      return;
    }

    await correctRecord.mutateAsync({
      recordId: record.id,
      data: { record_data: parsed, correction_reason: reason },
    });
    onSuccess?.();
  }

  return (
    <Card title="Submit Correction">
      <p className="mb-3 text-xs text-gray-500">
        Creates a new version. The original record is preserved.
      </p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="record-data"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Record Data (JSON)
          </label>
          <textarea
            id="record-data"
            className={`block w-full rounded-md border px-3 py-2 font-mono text-sm ${
              parseError
                ? "border-red-300 focus:ring-red-500"
                : "border-gray-300 focus:ring-blue-500"
            } focus:outline-none focus:ring-2`}
            rows={12}
            value={editedData}
            onChange={(e) => {
              setEditedData(e.target.value);
              setParseError("");
            }}
            required
          />
          {parseError && (
            <p className="mt-1 text-sm text-red-600" role="alert">
              {parseError}
            </p>
          )}
        </div>
        <TextArea
          label="Correction Reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why is this correction needed?"
          required
        />
        <div className="flex justify-end">
          <Button type="submit" loading={correctRecord.isPending}>
            Submit Correction
          </Button>
        </div>
      </form>
    </Card>
  );
}
