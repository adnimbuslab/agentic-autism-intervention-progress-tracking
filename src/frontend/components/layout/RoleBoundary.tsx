"use client";

import { useAuth } from "@/lib/auth";
import { isInterventionist, isContributor } from "@/lib/utils/roleGuards";
import type { ReactNode } from "react";

interface RoleBoundaryProps {
  allow: "interventionist" | "contributor";
  children: ReactNode;
  fallback?: ReactNode;
}

export function RoleBoundary({ allow, children, fallback = null }: RoleBoundaryProps) {
  const { user } = useAuth();
  if (!user) return null;

  if (allow === "interventionist" && !isInterventionist(user)) return <>{fallback}</>;
  if (allow === "contributor" && !isContributor(user)) return <>{fallback}</>;

  return <>{children}</>;
}
