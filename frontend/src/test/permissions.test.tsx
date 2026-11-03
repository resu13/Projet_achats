import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, Can } from '../app/AuthContext'
import { personas } from '../mocks/data'
import type { Permission } from '../types'

afterEach(cleanup)

const checkedPermissions: Permission[] = [
  'scanner',
  'supprimer',
  'annuler_br',
  'voir_audit',
  'gerer_utilisateurs',
  'generer_br',
]

describe.each(personas)('$label', (persona) => {
  it('n’affiche que les commandes autorisées par les permissions de l’API', () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } })
    client.setQueryData(['me'], persona.me)
    render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          {checkedPermissions.map((permission) => (
            <Can permission={permission} key={permission}>
              <span>{permission}</span>
            </Can>
          ))}
        </AuthProvider>
      </QueryClientProvider>,
    )

    for (const permission of checkedPermissions) {
      expect(screen.queryByText(permission) !== null).toBe(persona.me.permissions.includes(permission))
    }
    const canScan = persona.me.permissions.includes('scanner')
    expect(persona.me.types_scannables.includes('BL')).toBe(canScan)
    expect(persona.me.types_scannables.includes('FACTURE')).toBe(canScan && persona.me.permissions.includes('voir_tous'))
  })
})
