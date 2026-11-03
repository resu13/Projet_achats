import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import App from '../app/App'
import { AuthContext } from '../app/auth-context'
import { personas } from '../mocks/data'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const expectedWorkspaces: Record<string, { title: string; firstAction: string }> = {
  'odoo:operateur': { title: 'Espace magasin', firstAction: 'Scanner un BL' },
  'odoo:comptable': { title: 'Espace comptabilité', firstAction: 'Scanner une facture' },
  'odoo:responsable': { title: 'Espace responsable', firstAction: 'Suivi des commandes' },
  'odoo:lecteur': { title: 'Espace consultation', firstAction: 'Bons de commande' },
  'odoo:admin': { title: 'Administration Odoo', firstAction: 'Gérer les utilisateurs' },
  'urium:magasinier': { title: 'Espace magasin', firstAction: 'Créer un bon de réception' },
  'urium:achats': { title: 'Espace service achats', firstAction: 'Commandes à réceptionner' },
  'urium:directeur': { title: 'Espace direction', firstAction: 'Suivi des commandes' },
  'urium:admin': { title: 'Administration Urium', firstAction: 'Gérer les utilisateurs' },
}

describe.each(personas)('$label workspace', (persona) => {
  it('shows role-specific workspace and permitted shortcuts', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    const path = `${persona.me.entreprise.erp_type}:${persona.me.utilisateur.role}`
    const expected = expectedWorkspaces[path]
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), window.location.origin)
      const data = url.pathname === '/api/tableau-de-bord'
        ? {
            scansParJour: [],
            labelsScans: [],
            dossiersIncomplets: 0,
            echecs: 0,
            brDuJour: 0,
            date: 'Aujourd’hui',
            dateIso: '2026-11-03',
          }
        : url.pathname === '/api/journal' || url.pathname === '/api/bc' || url.pathname === '/api/scans'
          ? []
          : null
      if (data === null) throw new Error(`Unexpected request: ${url.pathname}`)
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }))

    render(
      <QueryClientProvider client={client}>
        <AuthContext.Provider value={{
          me: persona.me,
          loading: false,
          error: null,
          can: (permission) => persona.me.permissions.includes(permission),
        }}>
          <MemoryRouter initialEntries={['/']}>
            <App />
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>,
    )

    expect(await screen.findByText(expected.title)).toBeTruthy()
    expect((await screen.findAllByRole('link', { name: new RegExp(expected.firstAction) })).length).toBeGreaterThan(0)
    if (!persona.me.permissions.includes('gerer_utilisateurs')) {
      expect(screen.queryByRole('link', { name: /Gérer les utilisateurs/ })).toBeNull()
    }
  })
})
