import { useContext } from 'react'
import type { Permission } from '../types'
import { AuthContext } from './auth-context'

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth doit être utilisé dans AuthProvider.')
  return context
}

export function useCan(permission: Permission) {
  return useAuth().can(permission)
}
