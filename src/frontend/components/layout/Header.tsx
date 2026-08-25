"use client";

import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/Button";

export function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-4 lg:px-6">
      <span className="text-sm font-semibold text-gray-900">
        Intervention Tracker
      </span>
      {user && (
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-600">
            {user.email}
          </span>
          <Button variant="ghost" size="sm" onClick={logout}>
            Sign Out
          </Button>
        </div>
      )}
    </header>
  );
}
