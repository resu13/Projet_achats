import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { request } from '../api/client'
import type { MeResponse, Permission } from '../types'
import { AuthContext } from './auth-context'
import type { AuthValue } from './auth-context'
import { useCan } from './useAuth'

export function AuthProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: ['me'],
    queryFn: () => request<MeResponse>('/api/me'),
  })

  const value: AuthValue = {
    me: query.data,
    loading: query.isPending,
    error: query.error,
    can: (permission) => query.data?.permissions.includes(permission) ?? false,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function Can({
  permission,
  children,
}: {
  permission: Permission
  children: ReactNode
}) {
  return useCan(permission) ? children : null
}
