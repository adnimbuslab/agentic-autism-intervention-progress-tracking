"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { isInterventionist } from "@/lib/utils/roleGuards";

interface NavItem {
  label: string;
  href: string;
}

const interventionistNav: NavItem[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Children", href: "/children" },
];

const contributorNav: NavItem[] = [
  { label: "Home", href: "/contribute" },
];

export function Sidebar() {
  const { user } = useAuth();
  const pathname = usePathname();

  if (!user) return null;

  const navItems = isInterventionist(user) ? interventionistNav : contributorNav;

  return (
    <aside className="hidden w-56 shrink-0 border-r border-gray-200 bg-white lg:block">
      <nav className="flex flex-col gap-1 p-3" aria-label="Main navigation">
        {navItems.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-blue-50 text-blue-700"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              }`}
              aria-current={active ? "page" : undefined}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
