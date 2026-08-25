'use client'

import Link from 'next/link'
import { useChildren } from '@/lib/hooks/useChildren'
import { LoadingState } from '@/components/common/LoadingState'
import { ErrorState } from '@/components/common/ErrorState'
import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'

export default function DashboardPage() {
  const { data: children, isLoading, error } = useChildren()

  if (isLoading) return <LoadingState message="Loading dashboard..." />
  if (error) return <ErrorState error={error} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <Link
          href="/children"
          className="text-sm font-medium text-blue-600 hover:text-blue-800"
        >
          View all children
        </Link>
      </div>

      {!children?.length ? (
        <EmptyState
          title="No children assigned"
          description="Create a child profile to begin tracking observations."
          actionLabel="Add Child"
          actionHref="/children"
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {children.map((child) => (
            <Link key={child.id} href={`/children/${child.id}`}>
              <Card className="transition-shadow hover:shadow-md">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium">{child.display_name}</h3>
                  <Badge variant={child.is_active ? 'success' : 'neutral'}>
                    {child.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-gray-500">
                  Created {new Date(child.created_at).toLocaleDateString()}
                </p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
