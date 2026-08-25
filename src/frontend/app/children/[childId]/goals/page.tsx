'use client'

import { useState } from 'react'
import { useParams } from 'next/navigation'
import { useGoals, useCreateGoal } from '@/lib/hooks/useGoals'
import { LoadingState } from '@/components/common/LoadingState'
import { ErrorState } from '@/components/common/ErrorState'
import { EmptyState } from '@/components/common/EmptyState'
import { GoalCard } from '@/components/goals/GoalCard'
import { GoalForm } from '@/components/goals/GoalForm'
import { Button } from '@/components/ui/Button'

export default function GoalsPage() {
  const { childId } = useParams<{ childId: string }>()
  const { data: goals, isLoading, error } = useGoals(childId)
  const createGoal = useCreateGoal()
  const [showForm, setShowForm] = useState(false)

  if (isLoading) return <LoadingState />
  if (error) return <ErrorState error={error} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Goals</h2>
        <Button onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : 'Add Goal'}
        </Button>
      </div>

      {showForm && (
        <GoalForm
          onSubmit={async (data) => {
            await createGoal.mutateAsync({ childId, data })
            setShowForm(false)
          }}
          loading={createGoal.isPending}
        />
      )}

      {!goals?.length ? (
        <EmptyState
          title="No goals"
          description="Create goals to track intervention progress."
        />
      ) : (
        <div className="space-y-3">
          {goals.map((goal) => (
            <GoalCard key={goal.id} goal={goal} />
          ))}
        </div>
      )}
    </div>
  )
}
