"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Card } from "@/components/ui/Card";
import { useInviteActor } from "@/lib/hooks/useActors";
import type { Role } from "@/lib/types";

const roleOptions = [
  { label: "Parent", value: "parent" },
  { label: "Teacher", value: "teacher" },
  { label: "Trainer", value: "trainer" },
  { label: "EPA", value: "epa" },
  { label: "Secondary Interventionist", value: "secondary_interventionist" },
];

interface ActorInviteFormProps {
  childId: string;
  onSuccess?: () => void;
}

export function ActorInviteForm({ childId, onSuccess }: ActorInviteFormProps) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("parent");
  const invite = useInviteActor();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await invite.mutateAsync({
      childId,
      data: { email, role },
    });
    setEmail("");
    onSuccess?.();
  }

  return (
    <Card title="Invite Contributor">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Select
          label="Role"
          options={roleOptions}
          value={role}
          onChange={(e) => setRole(e.target.value as Role)}
        />
        <div className="flex justify-end">
          <Button type="submit" loading={invite.isPending}>
            Send Invitation
          </Button>
        </div>
      </form>
    </Card>
  );
}
