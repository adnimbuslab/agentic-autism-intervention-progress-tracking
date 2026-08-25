"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { isInterventionist } from "@/lib/utils/roleGuards";
import { AppShell } from "@/components/layout/AppShell";

export default function ContributeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/");
    }
  }, [isLoading, user, router]);

  useEffect(() => {
    if (user && isInterventionist(user)) {
      router.replace("/dashboard");
    }
  }, [user, router]);

  if (isLoading || !user) return null;

  return <AppShell>{children}</AppShell>;
}
