"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { Select } from "@/components/ui/Select";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import {
  useSubmitObservation,
  useClarification,
  useFinalizeObservation,
} from "@/lib/hooks/useObservations";
import type { Setting, ObservationSubmitResponse } from "@/lib/types";

const settingOptions = [
  { label: "Home", value: "home" },
  { label: "School", value: "school" },
  { label: "Clinic", value: "clinic" },
  { label: "Community", value: "community" },
  { label: "Other", value: "other" },
];

interface ConversationalCaptureProps {
  childId: string;
  onComplete?: () => void;
}

type Phase = "compose" | "clarifying" | "done" | "error";

export function ConversationalCapture({
  childId,
  onComplete,
}: ConversationalCaptureProps) {
  const [phase, setPhase] = useState<Phase>("compose");
  const [rawText, setRawText] = useState("");
  const [setting, setSetting] = useState<Setting>("home");
  const [currentResponse, setCurrentResponse] =
    useState<ObservationSubmitResponse | null>(null);
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const submitObs = useSubmitObservation();
  const submitClarification = useClarification();
  const finalizeObs = useFinalizeObservation();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const res = await submitObs.mutateAsync({
        childId,
        data: { raw_text: rawText, setting },
      });
      handleResponse(res);
    } catch {
      setPhase("error");
      setErrorMessage("Failed to submit observation.");
    }
  }

  function handleResponse(res: ObservationSubmitResponse) {
    setCurrentResponse(res);
    if (res.observation.status === "clarifying" && res.clarification_question) {
      setPhase("clarifying");
      setClarificationAnswer("");
    } else if (res.observation.status === "finalized") {
      setPhase("done");
      onComplete?.();
    } else if (res.observation.status === "failed") {
      setPhase("error");
      setErrorMessage("Observation processing failed.");
    } else {
      setPhase("done");
      onComplete?.();
    }
  }

  async function handleClarificationSubmit(answer: string, declined: boolean) {
    if (!currentResponse) return;
    try {
      const res = await submitClarification.mutateAsync({
        obsId: currentResponse.observation.id,
        data: declined
          ? { answer: "", declined: true }
          : { answer, declined: false },
      });
      handleResponse(res);
    } catch {
      setPhase("error");
      setErrorMessage("Failed to submit response.");
    }
  }

  async function handleFinalize() {
    if (!currentResponse) return;
    try {
      await finalizeObs.mutateAsync({
        obsId: currentResponse.observation.id,
        childId,
      });
      setPhase("done");
      onComplete?.();
    } catch {
      setPhase("error");
      setErrorMessage("Failed to finalize observation.");
    }
  }

  if (phase === "done") {
    return (
      <Card>
        <div className="py-6 text-center">
          <Badge variant="success" className="mb-2">
            Submitted
          </Badge>
          <p className="text-sm text-gray-600">
            Your observation has been recorded. Thank you!
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-4"
            onClick={() => {
              setPhase("compose");
              setRawText("");
              setCurrentResponse(null);
            }}
          >
            Submit Another
          </Button>
        </div>
      </Card>
    );
  }

  if (phase === "error") {
    return (
      <Card>
        <div className="py-6 text-center" role="alert">
          <p className="text-sm text-red-600">{errorMessage}</p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-4"
            onClick={() => setPhase("compose")}
          >
            Try Again
          </Button>
        </div>
      </Card>
    );
  }

  if (phase === "clarifying" && currentResponse?.clarification_question) {
    return (
      <Card title="Quick Question">
        <div className="space-y-4">
          <div className="rounded-md bg-blue-50 p-3">
            <p className="text-sm text-blue-800">
              {currentResponse.clarification_question}
            </p>
          </div>
          <TextArea
            label="Your answer"
            value={clarificationAnswer}
            onChange={(e) => setClarificationAnswer(e.target.value)}
            placeholder="Type your answer..."
          />
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() =>
                handleClarificationSubmit(clarificationAnswer, false)
              }
              loading={submitClarification.isPending}
              disabled={!clarificationAnswer.trim()}
            >
              Send
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleClarificationSubmit("I don't know", true)}
              loading={submitClarification.isPending}
            >
              I don&apos;t know
            </Button>
            <Button
              variant="ghost"
              onClick={() => handleClarificationSubmit("", true)}
              loading={submitClarification.isPending}
            >
              Skip
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card title="New Observation">
      <form onSubmit={handleSubmit} className="space-y-4">
        <TextArea
          label="What did you observe?"
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          placeholder="Describe what happened in your own words..."
          required
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Setting"
            options={settingOptions}
            value={setting}
            onChange={(e) => setSetting(e.target.value as Setting)}
          />
          <div />
        </div>
        <div className="flex justify-end">
          <Button type="submit" loading={submitObs.isPending}>
            Submit Observation
          </Button>
        </div>
      </form>
    </Card>
  );
}
