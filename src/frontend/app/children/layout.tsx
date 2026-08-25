"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { isContributor } from "@/lib/utils/roleGuards";
import { AppShell } from "@/components/layout/AppShell";

export default function ChildrenLayout({
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
    if (user && isContributor(user)) {
      router.replace("/contribute");
    }
  }, [user, router]);

  if (isLoading || !user) return null;

  return <AppShell>{children}</AppShell>;
}
