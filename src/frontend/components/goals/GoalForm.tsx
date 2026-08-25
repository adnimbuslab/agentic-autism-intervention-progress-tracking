"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TextArea } from "@/components/ui/TextArea";
import { Card } from "@/components/ui/Card";
import type { GoalCreateRequest, Domain, GoalType } from "@/lib/types";

const domainOptions = [
  { label: "Social Communication", value: "social_communication" },
  { label: "Language", value: "language" },
  { label: "Play", value: "play" },
  { label: "Behavior", value: "behavior" },
  { label: "Motor", value: "motor" },
  { label: "Cognitive", value: "cognitive" },
  { label: "Adaptive", value: "adaptive" },
  { label: "Sensory", value: "sensory" },
];

const goalTypeOptions = [
  { label: "Long Term", value: "long_term" },
  { label: "Short Term", value: "short_term" },
];

interface GoalFormProps {
  onSubmit: (data: GoalCreateRequest) => Promise<void>;
  loading?: boolean;
}

export function GoalForm({ onSubmit, loading }: GoalFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [domain, setDomain] = useState<Domain>("social_communication");
  const [goalType, setGoalType] = useState<GoalType>("short_term");
  const [targetDate, setTargetDate] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await onSubmit({
      title,
      description,
      domain,
      goal_type: goalType,
      target_date: targetDate || null,
    });
    setTitle("");
    setDescription("");
    setTargetDate("");
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Goal Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Domain"
            options={domainOptions}
            value={domain}
            onChange={(e) => setDomain(e.target.value as Domain)}
          />
          <Select
            label="Type"
            options={goalTypeOptions}
            value={goalType}
            onChange={(e) => setGoalType(e.target.value as GoalType)}
          />
        </div>
        <TextArea
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <Input
          label="Target Date"
          type="date"
          value={targetDate}
          onChange={(e) => setTargetDate(e.target.value)}
        />
        <div className="flex justify-end">
          <Button type="submit" loading={loading}>
            Create Goal
          </Button>
        </div>
      </form>
    </Card>
  );
}
