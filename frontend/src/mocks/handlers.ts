import { delay, http, HttpResponse } from 'msw'
import { activity, personas, purchaseOrders, scannedDocuments } from './data'
import type { DocumentType, Permission, Receipt, ScannedDocument } from '../types'

const activePersona = () => {
  const selected = localStorage.getItem('achats:persona')
  return personas.find((item) => item.id === selected) ?? personas[0]
}

const mockUsers = personas.map(({ id, me }) => ({
  id,
  nom: me.utilisateur.nom,
  identifiant: id,
  role: me.utilisateur.role,
  entreprise: me.entreprise.nom,
  codeEntreprise: me.entreprise.code,
  actif: true,
}))

const requirePermission = (permission: Permission) => {
  if (activePersona().me.permissions.includes(permission)) return null
  return HttpResponse.json({ message: 'Accès refusé : vous ne disposez pas des droits nécessaires.' }, { status: 403 })
}

const receipts: Receipt[] = [
  { id: 38, reference: 'BR-2026-0038', bcId: 148, statut: 'brouillon', lignes: [] },
]

const isValidReceiptLines = (bcId: number, lines: Receipt['lignes']) => {
  const order = purchaseOrders.find((item) => item.id === bcId)
  if (!order) return false
  return lines.every((line) => {
    const orderedLine = order.lignes.find((item) => item.article === line.article)
    return orderedLine !== undefined && line.quantite >= 0 && line.quantite <= orderedLine.commande - orderedLine.recue
  })
}

export const handlers = [
  http.get('/api/auth/login', () => HttpResponse.json({ csrfToken: 'demo-csrf-token' })),
  http.post('/api/auth/login', async ({ request }) => {
    const body = await request.json() as { username?: string; password?: string }
    if (!body.username || !body.password) {
      return HttpResponse.json({ message: 'Identifiant et mot de passe obligatoires.' }, { status: 400 })
    }
    return HttpResponse.json(activePersona().me)
  }),
  http.post('/api/auth/logout', () => HttpResponse.json({ detail: 'Déconnexion réussie.' })),
  http.post('/api/auth/changer-mot-de-passe/', () => HttpResponse.json({ detail: 'Mot de passe modifié avec succès.' })),
  http.get('/api/me', async () => {
    await delay(120)
    return HttpResponse.json(activePersona().me)
  }),
  http.get('/api/bc', async ({ request }) => {
    const user = activePersona().me
    if (!user.permissions.some((permission) => ['scanner', 'voir_siens', 'voir_tous', 'generer_br'].includes(permission))) {
      return HttpResponse.json({ message: 'Accès refusé : vous ne disposez pas des droits nécessaires.' }, { status: 403 })
    }
    await delay(180)
    const url = new URL(request.url)
    const search = (url.searchParams.get('recherche') ?? '').toLocaleLowerCase('fr')
    const incompleteOnly = url.searchParams.get('incomplets') === 'true'
    const fournisseur = url.searchParams.get('fournisseur') ?? ''
    const period = Number(url.searchParams.get('periode') ?? 0)
    const dateLimit = period ? new Date(Date.now() - period * 24 * 60 * 60 * 1000).toISOString().slice(0, 10) : ''
    const results = purchaseOrders.filter((order) => {
      const matchesText = `${order.reference} ${order.fournisseur}`.toLocaleLowerCase('fr').includes(search)
      const matchesIncomplete = !incompleteOnly || order.completude < 100
      const matchesSupplier = !fournisseur || order.fournisseur === fournisseur
      const matchesPeriod = !dateLimit || order.date >= dateLimit
      return matchesText && matchesIncomplete && matchesSupplier && matchesPeriod
    })
    return HttpResponse.json(results)
  }),
  http.get('/api/bc/:id', async ({ params }) => {
    const user = activePersona().me
    if (!user.permissions.some((permission) => ['scanner', 'voir_siens', 'voir_tous', 'generer_br'].includes(permission))) {
      return HttpResponse.json({ message: 'Accès refusé : vous ne disposez pas des droits nécessaires.' }, { status: 403 })
    }
    const order = purchaseOrders.find((item) => item.id === Number(params.id))
    if (!order) return HttpResponse.json({ message: 'Bon de commande introuvable.' }, { status: 404 })
    return HttpResponse.json({
      ...order,
      documents: scannedDocuments.filter((document) =>
        document.bc.includes(order.reference)
        && (user.permissions.includes('voir_tous') || document.auteur === user.utilisateur.nom),
      ),
      receptions: receipts.filter((receipt) => receipt.bcId === order.id),
    })
  }),
  http.get('/api/scans', async ({ request }) => {
    const user = activePersona().me
    if (!user.permissions.includes('voir_tous') && !user.permissions.includes('voir_siens')) {
      return HttpResponse.json({ message: 'Accès refusé : vous ne disposez pas des droits nécessaires.' }, { status: 403 })
    }
    const url = new URL(request.url)
    const type = url.searchParams.get('type')
    const status = url.searchParams.get('statut')
    const period = Number(url.searchParams.get('periode') ?? 0)
    const dateLimit = period ? new Date(Date.now() - period * 24 * 60 * 60 * 1000).toISOString().slice(0, 10) : ''
    const query = (url.searchParams.get('recherche') ?? '').toLocaleLowerCase('fr')
    const filtered = scannedDocuments.filter((document) =>
      (user.permissions.includes('voir_tous') || document.auteur === user.utilisateur.nom)
      &&
      (!type || document.type === type)
      && (!status || document.statut === status)
      && (!dateLimit || document.date.slice(0, 10) >= dateLimit)
      && `${document.numero} ${document.fournisseur} ${document.bc.join(' ')}`.toLocaleLowerCase('fr').includes(query),
    )
    return HttpResponse.json(filtered)
  }),
  http.get('/api/scans/:id', ({ params }) => {
    const document = scannedDocuments.find((item) => item.id === Number(params.id))
    if (!document) return HttpResponse.json({ message: 'Document introuvable.' }, { status: 404 })
    const user = activePersona().me
    if (!user.permissions.includes('voir_tous') && (!user.permissions.includes('voir_siens') || document.auteur !== user.utilisateur.nom)) {
      return HttpResponse.json({ message: 'Accès refusé : vous ne disposez pas des droits nécessaires.' }, { status: 403 })
    }
    return HttpResponse.json(document)
  }),
  http.post('/api/scans', async ({ request }) => {
    const denied = requirePermission('scanner')
    if (denied) return denied
    const form = await request.formData()
    const file = form.get('fichier')
    const type = form.get('type')
    const numero = form.get('numero_document')
    const links = form.get('ids_bc')
    if (!(file instanceof File) || typeof type !== 'string' || typeof numero !== 'string') {
      return HttpResponse.json({ message: 'Les informations du document sont incomplètes.' }, { status: 400 })
    }
    if (!activePersona().me.types_scannables.includes(type as DocumentType)) {
      return HttpResponse.json({ message: 'Ce type de document n’est pas autorisé pour votre compte.' }, { status: 403 })
    }
    if (file.size === 0 || file.size > 20 * 1024 * 1024) {
      return HttpResponse.json({ message: 'Fichier vide ou trop lourd. La taille maximale est de 20 Mo.' }, { status: 400 })
    }
    if (!['application/pdf', 'image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      return HttpResponse.json({ message: 'Format refusé. Choisissez un fichier JPEG, PNG ou PDF.' }, { status: 400 })
    }
    let bcIds: number[] = []
    if (typeof links === 'string') {
      try {
        const parsed: unknown = JSON.parse(links)
        if (Array.isArray(parsed) && parsed.every((value) => typeof value === 'number')) bcIds = parsed
      } catch (error) {
        if (!(error instanceof SyntaxError)) throw error
        return HttpResponse.json({ message: 'La liste des bons de commande est invalide.' }, { status: 400 })
      }
    }
    if (bcIds.length === 0) return HttpResponse.json({ message: 'Sélectionnez au moins un bon de commande.' }, { status: 400 })
    const linkedOrders = purchaseOrders.filter((order) => bcIds.includes(order.id))
    if (linkedOrders.length !== bcIds.length) return HttpResponse.json({ message: 'Un bon de commande sélectionné est introuvable.' }, { status: 404 })
    const duplicate = scannedDocuments.some((document) => document.numero.toLocaleLowerCase('fr') === numero.toLocaleLowerCase('fr'))
    if (duplicate) return HttpResponse.json({ message: 'Ce numéro de document existe déjà.' }, { status: 409 })
    const created: ScannedDocument = {
      id: Date.now(),
      type: type as ScannedDocument['type'],
      numero,
      fournisseur: linkedOrders[0]?.fournisseur ?? 'Fournisseur sélectionné',
      bc: linkedOrders.map((order) => order.reference),
      statut: 'en_attente',
      auteur: activePersona().me.utilisateur.nom,
      date: new Date().toISOString(),
    }
    scannedDocuments.unshift(created)
    return HttpResponse.json(created, { status: 201 })
  }),
  http.patch('/api/scans/:id', async ({ params, request }) => {
    const denied = requirePermission('remplacer')
    if (denied) return denied
    const document = scannedDocuments.find((item) => item.id === Number(params.id))
    if (!document) return HttpResponse.json({ message: 'Document introuvable.' }, { status: 404 })
    const form = await request.formData()
    const file = form.get('fichier')
    if (!(file instanceof File) || file.size === 0 || file.size > 20 * 1024 * 1024) {
      return HttpResponse.json({ message: 'Choisissez un fichier de remplacement.' }, { status: 400 })
    }
    if (!['application/pdf', 'image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      return HttpResponse.json({ message: 'Format refusé. Choisissez un fichier JPEG, PNG ou PDF.' }, { status: 400 })
    }
    document.statut = 'en_attente'
    delete document.messageErreur
    return HttpResponse.json(document)
  }),
  http.delete('/api/scans/:id', ({ params }) => {
    const denied = requirePermission('supprimer')
    if (denied) return denied
    const index = scannedDocuments.findIndex((item) => item.id === Number(params.id))
    if (index < 0) return HttpResponse.json({ message: 'Document introuvable.' }, { status: 404 })
    const [removed] = scannedDocuments.splice(index, 1)
    return HttpResponse.json(removed)
  }),
  http.post('/api/scans/:id/resynchroniser', ({ params }) => {
    const denied = requirePermission('resynchroniser')
    if (denied) return denied
    const document = scannedDocuments.find((item) => item.id === Number(params.id))
    if (!document) return HttpResponse.json({ message: 'Document introuvable.' }, { status: 404 })
    document.statut = 'en_attente'
    delete document.messageErreur
    return HttpResponse.json(document)
  }),
  http.post('/api/bc/:id/br', async ({ params, request }) => {
    const denied = requirePermission('generer_br')
    if (denied) return denied
    const order = purchaseOrders.find((item) => item.id === Number(params.id))
    if (!order) return HttpResponse.json({ message: 'Bon de commande introuvable.' }, { status: 404 })
    const body = await request.json() as { lignes?: Array<{ article: string; quantite: number }>; numeroBl?: string; remarques?: string }
    if (body.lignes && !isValidReceiptLines(order.id, body.lignes)) return HttpResponse.json({ message: 'Une quantité dépasse le reste à recevoir.' }, { status: 400 })
    if ((body.lignes ?? []).some((line) => line.quantite < 0)) return HttpResponse.json({ message: 'Les quantités ne peuvent pas être négatives.' }, { status: 400 })
    const receipt: Receipt = {
      id: Date.now(),
      reference: `BR-2026-${String(receipts.length + 39).padStart(4, '0')}`,
      bcId: order.id,
      statut: 'brouillon',
      lignes: body.lignes ?? [],
      numeroBl: body.numeroBl,
      remarques: body.remarques,
    }
    receipts.unshift(receipt)
    return HttpResponse.json(receipt, { status: 201 })
  }),
  http.patch('/api/br/:id', async ({ params, request }) => {
    const denied = requirePermission('generer_br')
    if (denied) return denied
    const receipt = receipts.find((item) => item.id === Number(params.id))
    if (!receipt) return HttpResponse.json({ message: 'Bon de réception introuvable.' }, { status: 404 })
    const body = await request.json() as { lignes?: Receipt['lignes']; numeroBl?: string; remarques?: string }
    if (body.lignes && !isValidReceiptLines(receipt.bcId, body.lignes)) return HttpResponse.json({ message: 'Une quantité dépasse le reste à recevoir.' }, { status: 400 })
    if (body.lignes) receipt.lignes = body.lignes
    if (body.numeroBl !== undefined) receipt.numeroBl = body.numeroBl
    if (body.remarques !== undefined) receipt.remarques = body.remarques
    return HttpResponse.json(receipt)
  }),
  http.post('/api/br/:id/valider', async ({ params, request }) => {
    const denied = requirePermission('generer_br')
    if (denied) return denied
    const receipt = receipts.find((item) => item.id === Number(params.id))
    if (!receipt) return HttpResponse.json({ message: 'Bon de réception introuvable.' }, { status: 404 })
    if (receipt.statut !== 'brouillon') return HttpResponse.json({ message: 'Ce bon de réception a déjà été traité.' }, { status: 409 })
    const body = await request.json() as { mot_de_passe?: string }
    if (!receipt.lignes.some((line) => line.quantite > 0) || !isValidReceiptLines(receipt.bcId, receipt.lignes)) {
      return HttpResponse.json({ message: 'Le brouillon contient des quantités invalides.' }, { status: 400 })
    }
    if (activePersona().me.options.reauth_validation_br && !body.mot_de_passe) {
      return HttpResponse.json({ message: 'Le mot de passe est obligatoire pour valider cette réception.' }, { status: 400 })
    }
    receipt.statut = 'valide'
    return HttpResponse.json(receipt)
  }),
  http.post('/api/br/:id/annuler', async ({ params, request }) => {
    const denied = requirePermission('annuler_br')
    if (denied) return denied
    const receipt = receipts.find((item) => item.id === Number(params.id))
    if (!receipt) return HttpResponse.json({ message: 'Bon de réception introuvable.' }, { status: 404 })
    const body = await request.json() as { motif?: string }
    if (!body.motif?.trim()) return HttpResponse.json({ message: 'Le motif d’annulation est obligatoire.' }, { status: 400 })
    receipt.statut = 'annule'
    return HttpResponse.json(receipt)
  }),
  http.get('/api/br/:id/pdf', async ({ params }) => {
    const user = activePersona().me
    if (!user.permissions.includes('generer_br') && !user.permissions.includes('voir_tous')) {
      return HttpResponse.json({ message: 'Accès refusé : vous ne disposez pas des droits nécessaires.' }, { status: 403 })
    }
    const receipt = receipts.find((item) => item.id === Number(params.id))
    if (!receipt) return HttpResponse.json({ message: 'Bon de réception introuvable.' }, { status: 404 })
    const { PDFDocument, StandardFonts, rgb } = await import('pdf-lib')
    const pdf = await PDFDocument.create()
    const page = pdf.addPage([595, 842])
    const font = await pdf.embedFont(StandardFonts.Helvetica)
    const order = purchaseOrders.find((item) => item.id === receipt.bcId)
    page.drawText('BON DE RECEPTION', { x: 52, y: 780, size: 18, font, color: rgb(0.13, 0.3, 0.38) })
    page.drawText(receipt.reference, { x: 52, y: 744, size: 13, font })
    page.drawText(`Commande : ${order?.reference ?? receipt.bcId}`, { x: 52, y: 715, size: 11, font })
    page.drawText(`Fournisseur : ${order?.fournisseur ?? '—'}`, { x: 52, y: 695, size: 11, font })
    receipt.lignes.forEach((line, index) => {
      page.drawText(`${line.article} — ${line.quantite}`, { x: 52, y: 650 - index * 19, size: 10, font })
    })
    page.drawText('Validation électronique', { x: 52, y: 58, size: 9, font, color: rgb(0.25, 0.5, 0.4) })
    const bytes = await pdf.save()
    const output = new ArrayBuffer(bytes.byteLength)
    new Uint8Array(output).set(bytes)
    return new HttpResponse(output, { headers: { 'Content-Type': 'application/pdf' } })
  }),
  http.get('/api/journal', () => {
    const denied = requirePermission('voir_audit')
    if (denied) return denied
    return HttpResponse.json(activity)
  }),
  http.get('/api/utilisateurs', () => {
    const denied = requirePermission('gerer_utilisateurs')
    if (denied) return denied
    const companyCode = activePersona().me.entreprise.code
    const rolesDisponibles = activePersona().me.entreprise.erp_type === 'odoo'
      ? ['operateur', 'comptable', 'responsable', 'lecteur', 'admin']
      : ['magasinier', 'achats', 'directeur', 'admin']
    return HttpResponse.json({
      utilisateurs: mockUsers.filter((user) => user.codeEntreprise === companyCode),
      rolesDisponibles,
    })
  }),
  http.post('/api/utilisateurs', async ({ request }) => {
    const denied = requirePermission('gerer_utilisateurs')
    if (denied) return denied
    const body = await request.json() as { nom?: string; role?: string }
    if (!body.nom?.trim() || !body.role?.trim()) return HttpResponse.json({ message: 'Le nom et le rôle sont obligatoires.' }, { status: 400 })
    const user = {
      id: `${activePersona().me.entreprise.code}-${Date.now()}`,
      nom: body.nom.trim(),
      identifiant: (body as { identifiant?: string }).identifiant?.trim() || `demo-${Date.now()}`,
      role: body.role.trim(),
      entreprise: activePersona().me.entreprise.nom,
      codeEntreprise: activePersona().me.entreprise.code,
      actif: true,
    }
    mockUsers.unshift(user)
    return HttpResponse.json({ ...user, mot_de_passe_temporaire: 'demo-password' }, { status: 201 })
  }),
  http.patch('/api/utilisateurs/:id', async ({ params, request }) => {
    const denied = requirePermission('gerer_utilisateurs')
    if (denied) return denied
    const user = mockUsers.find((item) => item.id === params.id && item.codeEntreprise === activePersona().me.entreprise.code)
    if (!user) return HttpResponse.json({ message: 'Utilisateur introuvable.' }, { status: 404 })
    const body = await request.json() as { role?: string; actif?: boolean; reset_password?: boolean }
    if ((body.actif === false || (body.role && body.role !== 'admin')) && user.role === 'admin' && user.actif) {
      const activeAdmins = mockUsers.filter((item) => item.codeEntreprise === user.codeEntreprise && item.role === 'admin' && item.actif)
      if (activeAdmins.length <= 1) return HttpResponse.json({ message: 'Le dernier administrateur ne peut pas être désactivé.' }, { status: 409 })
    }
    const allowedRoles = activePersona().me.entreprise.erp_type === 'odoo'
      ? ['operateur', 'comptable', 'responsable', 'lecteur', 'admin']
      : ['magasinier', 'achats', 'directeur', 'admin']
    if (body.role && !allowedRoles.includes(body.role)) return HttpResponse.json({ message: 'Ce rôle ne correspond pas à l’entreprise.' }, { status: 400 })
    if (body.role) user.role = body.role
    if (typeof body.actif === 'boolean') user.actif = body.actif
    return HttpResponse.json(body.reset_password ? { ...user, mot_de_passe_temporaire: 'demo-password' } : user)
  }),
  http.get('/api/tableau-de-bord', () => HttpResponse.json({
    scansParJour: [8, 12, 9, 17, 14, 21, 16],
    labelsScans: ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'],
    dossiersIncomplets: purchaseOrders.filter((order) => order.completude < 100).length,
    echecs: scannedDocuments.filter((document) => document.statut === 'echec').length,
    brDuJour: 3,
    date: new Intl.DateTimeFormat('fr-FR', { dateStyle: 'full' }).format(new Date()),
    dateIso: new Date().toISOString().slice(0, 10),
  })),
  http.get('/api/etat-services', () => HttpResponse.json({
    erp: { statut: 'synchronise', detail: 'Connexion ERP de démonstration.', verifieLe: new Date().toISOString() },
    drive: { statut: 'synchronise', detail: 'Accès Drive de démonstration.', verifieLe: new Date().toISOString() },
  })),
]
