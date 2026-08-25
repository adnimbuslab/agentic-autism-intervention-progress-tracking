'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useChildren } from '@/lib/hooks/useChildren'
import { useAuth } from '@/lib/auth'
import { isInterventionist } from '@/lib/utils/roleGuards'
import { LoadingState } from '@/components/common/LoadingState'
import { ErrorState } from '@/components/common/ErrorState'
import { EmptyState } from '@/components/common/EmptyState'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api } from '@/lib/api'
import { useMutation, useQueryClient } from '@tanstack/react-query'

export default function ChildrenPage() {
  const { user } = useAuth()
  const { data: children, isLoading, error } = useChildren()
  const [showCreate, setShowCreate] = useState(false)
  const [displayName, setDisplayName] = useState('')
  const queryClient = useQueryClient()

  const createChild = useMutation({
    mutationFn: (name: string) =>
      api.post('/children/', { display_name: name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['children'] })
      setShowCreate(false)
      setDisplayName('')
    },
  })

  if (isLoading) return <LoadingState />
  if (error) return <ErrorState error={error} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Children</h1>
        {user && isInterventionist(user) && (
          <Button onClick={() => setShowCreate(true)}>Add Child</Button>
        )}
      </div>

      {showCreate && (
        <Card>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              createChild.mutate(displayName)
            }}
            className="flex items-end gap-3"
          >
            <div className="flex-1">
              <Input
                label="Display Name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
              />
            </div>
            <Button type="submit" loading={createChild.isPending}>
              Create
            </Button>
            <Button
              variant="ghost"
              onClick={() => setShowCreate(false)}
            >
              Cancel
            </Button>
          </form>
        </Card>
      )}

      {!children?.length ? (
        <EmptyState
          title="No children"
          description="No children are assigned to you yet."
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
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
