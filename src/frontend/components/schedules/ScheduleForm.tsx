"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TextArea } from "@/components/ui/TextArea";
import { Card } from "@/components/ui/Card";
import { useCreateSchedule } from "@/lib/hooks/useSchedules";
import type { Goal, ActorAssignment, Setting } from "@/lib/types";

const settingOptions = [
  { label: "Any Setting", value: "" },
  { label: "Home", value: "home" },
  { label: "School", value: "school" },
  { label: "Clinic", value: "clinic" },
  { label: "Community", value: "community" },
  { label: "Other", value: "other" },
];

interface ScheduleFormProps {
  childId: string;
  goals?: Goal[];
  actors?: ActorAssignment[];
  onSuccess?: () => void;
}

export function ScheduleForm({
  childId,
  goals = [],
  actors = [],
  onSuccess,
}: ScheduleFormProps) {
  const [cadenceDays, setCadenceDays] = useState("7");
  const [goalId, setGoalId] = useState("");
  const [actorId, setActorId] = useState("");
  const [setting, setSetting] = useState("");
  const [description, setDescription] = useState("");
  const create = useCreateSchedule();

  const goalOptions = [
    { label: "Any Goal", value: "" },
    ...goals.map((g) => ({ label: g.title, value: g.id })),
  ];

  const actorOptions = [
    { label: "Any Contributor", value: "" },
    ...actors.map((a) => ({ label: a.invitation_email ?? a.user_id, value: a.id })),
  ];

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await create.mutateAsync({
      childId,
      data: {
        cadence_days: parseInt(cadenceDays, 10),
        goal_id: goalId || null,
        actor_id: actorId || null,
        setting: (setting as Setting) || null,
        description: description || null,
      },
    });
    setCadenceDays("7");
    setGoalId("");
    setActorId("");
    setSetting("");
    setDescription("");
    onSuccess?.();
  }

  return (
    <Card title="New Observation Schedule">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Cadence (days)"
          type="number"
          min="1"
          value={cadenceDays}
          onChange={(e) => setCadenceDays(e.target.value)}
          required
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Goal" options={goalOptions} value={goalId} onChange={(e) => setGoalId(e.target.value)} />
          <Select label="Contributor" options={actorOptions} value={actorId} onChange={(e) => setActorId(e.target.value)} />
        </div>
        <Select label="Setting" options={settingOptions} value={setting} onChange={(e) => setSetting(e.target.value)} />
        <TextArea
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <div className="flex justify-end">
          <Button type="submit" loading={create.isPending}>
            Create Schedule
          </Button>
        </div>
      </form>
    </Card>
  );
}
