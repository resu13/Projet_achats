import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '../app/AuthContext'
import { ReceiptPage } from '../app/App'
import { personas } from '../mocks/data'
import type { PurchaseOrder, Receipt } from '../types'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const order: PurchaseOrder = {
  id: 148,
  reference: 'BC-2026-0148',
  fournisseur: 'Alpha Logistics',
  date: '2026-10-28',
  statutErp: 'confirme',
  montant: 158420,
  devise: 'MAD',
  statutReception: 'partiellement_recu',
  completude: 68,
  lignes: [{ article: 'Câble électrique 3G2.5', commande: 5, recue: 2, unite: 'bobines' }],
  br: 1,
  bl: 1,
  factures: 0,
}

it('demande le mot de passe et empêche le double envoi à la validation du BR', async () => {
  const validationCalls: string[] = []
  const draft: Receipt = { id: 90, reference: 'BR-2026-0040', bcId: 148, statut: 'brouillon', lignes: [] }
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname === '/api/auth/login' && !init?.method) {
      return Response.json({ csrfToken: 'test-csrf-token' })
    }
    if (url.pathname === '/api/bc/148') return Response.json(order)
    if (url.pathname === '/api/bc/148/br' && init?.method === 'POST') return Response.json(draft)
    if (url.pathname === '/api/br/90/valider') {
      validationCalls.push(url.pathname)
      return Response.json({ ...draft, statut: 'valide' })
    }
    throw new Error(`Requête non mockée : ${url.pathname}`)
  })
  vi.stubGlobal('fetch', fetchMock)

  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  client.setQueryData(['me'], personas.find((item) => item.id === 'urium-admin')?.me)
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/bc/148/br']}>
        <AuthProvider>
          <Routes><Route path="/bc/:id/br" element={<ReceiptPage />} /></Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )

  await screen.findByText('Indiquez les quantités réceptionnées')
  fireEvent.click(screen.getByRole('button', { name: 'Tout recevoir' }))
  fireEvent.click(screen.getByRole('button', { name: /Valider la réception/ }))
  fireEvent.click(screen.getAllByRole('button', { name: /Valider la réception/ }).at(-1)!)
  expect(await screen.findByText('Saisissez votre mot de passe pour confirmer.')).toBeTruthy()
  expect(validationCalls).toHaveLength(0)

  fireEvent.change(screen.getByLabelText('Mot de passe'), { target: { value: 'demo-password' } })
  const confirmButton = screen.getAllByRole('button', { name: /Valider la réception/ }).at(-1)!
  fireEvent.click(confirmButton)
  fireEvent.click(confirmButton)

  await screen.findByText('Réception validée')
  await waitFor(() => expect(validationCalls).toHaveLength(1))
})
