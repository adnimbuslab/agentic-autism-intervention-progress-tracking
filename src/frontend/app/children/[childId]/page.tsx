'use client'

import { useParams } from 'next/navigation'
import Link from 'next/link'
import { useChild } from '@/lib/hooks/useChildren'
import { useGoals } from '@/lib/hooks/useGoals'
import { useObservations } from '@/lib/hooks/useObservations'
import { LoadingState } from '@/components/common/LoadingState'
import { ErrorState } from '@/components/common/ErrorState'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Tabs } from '@/components/ui/Tabs'

const tabs = [
  { label: 'Overview', value: 'overview' },
  { label: 'Goals', value: 'goals' },
  { label: 'Observations', value: 'observations' },
  { label: 'Records', value: 'records' },
  { label: 'Analytics', value: 'analytics' },
  { label: 'Reports', value: 'reports' },
  { label: 'Schedules', value: 'schedules' },
  { label: 'Contributors', value: 'actors' },
  { label: 'Audit', value: 'audit' },
]

export default function ChildOverviewPage() {
  const { childId } = useParams<{ childId: string }>()
  const { data: child, isLoading, error } = useChild(childId)
  const { data: goals } = useGoals(childId)
  const { data: observations } = useObservations(childId)

  if (isLoading) return <LoadingState />
  if (error) return <ErrorState error={error} />
  if (!child) return <ErrorState error={{ message: 'Child not found' }} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{child.display_name}</h1>
          <p className="text-sm text-gray-500">Child Workspace</p>
        </div>
        <Badge variant={child.is_active ? 'success' : 'neutral'}>
          {child.is_active ? 'Active' : 'Inactive'}
        </Badge>
      </div>

      <nav className="flex gap-1 overflow-x-auto border-b border-gray-200">
        {tabs.map((tab) => (
          <Link
            key={tab.value}
            href={`/children/${childId}/${tab.value === 'overview' ? '' : tab.value}`}
            className="whitespace-nowrap border-b-2 border-transparent px-4 py-2 text-sm font-medium text-gray-500 hover:border-gray-300 hover:text-gray-700"
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link href={`/children/${childId}/goals`}>
          <Card className="transition-shadow hover:shadow-md">
            <h3 className="font-medium text-gray-700">Goals</h3>
            <p className="mt-1 text-2xl font-semibold">
              {goals?.filter((g) => g.is_active).length ?? 0}
            </p>
            <p className="text-sm text-gray-500">Active goals</p>
          </Card>
        </Link>

        <Link href={`/children/${childId}/observations`}>
          <Card className="transition-shadow hover:shadow-md">
            <h3 className="font-medium text-gray-700">Observations</h3>
            <p className="mt-1 text-2xl font-semibold">
              {observations?.length ?? 0}
            </p>
            <p className="text-sm text-gray-500">Total observations</p>
          </Card>
        </Link>

        <Link href={`/children/${childId}/analytics`}>
          <Card className="transition-shadow hover:shadow-md">
            <h3 className="font-medium text-gray-700">Analytics</h3>
            <p className="text-sm text-gray-500 mt-2">
              View adequacy assessment and deterministic analytics
            </p>
          </Card>
        </Link>
      </div>

      {observations && observations.length > 0 && (
        <Card title="Recent Observations">
          <ul className="divide-y divide-gray-100">
            {observations.slice(0, 5).map((obs) => (
              <li key={obs.id} className="py-3">
                <Link
                  href={`/children/${childId}/observations/${obs.id}`}
                  className="block hover:bg-gray-50 -mx-1 px-1 rounded"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-gray-800 line-clamp-1">
                      {obs.raw_text}
                    </p>
                    <Badge
                      variant={
                        obs.status === 'finalized'
                          ? 'success'
                          : obs.status === 'failed'
                            ? 'error'
                            : 'warning'
                      }
                    >
                      {obs.status}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-gray-400">
                    {new Date(obs.submitted_at).toLocaleString()}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
