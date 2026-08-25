"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { Dialog } from "@/components/ui/Dialog";
import { useFlagReport } from "@/lib/hooks/useReports";

interface FlagButtonProps {
  reportId: string;
  isFlagged: boolean;
}

export function FlagButton({ reportId, isFlagged }: FlagButtonProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const flag = useFlagReport();

  async function handleFlag() {
    await flag.mutateAsync({
      reportId,
      data: { reason },
    });
    setOpen(false);
    setReason("");
  }

  return (
    <>
      <Button
        variant="danger"
        size="sm"
        onClick={() => setOpen(true)}
        disabled={isFlagged}
      >
        {isFlagged ? "Flagged" : "Flag Report"}
      </Button>

      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Flag This Report"
        actions={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleFlag}
              loading={flag.isPending}
              disabled={!reason.trim()}
            >
              Submit Flag
            </Button>
          </>
        }
      >
        <p className="mb-3">
          Flag this report to indicate it needs review or contains issues.
        </p>
        <TextArea
          label="Reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Describe the issue..."
          required
        />
      </Dialog>
    </>
  );
}
