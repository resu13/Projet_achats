import { createContext } from 'react'
import type { MeResponse, Permission } from '../types'

export interface AuthValue {
  me: MeResponse | undefined
  loading: boolean
  error: Error | null
  can: (permission: Permission) => boolean
}

export const AuthContext = createContext<AuthValue | null>(null)
