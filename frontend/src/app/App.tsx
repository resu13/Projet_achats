import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, FormEvent, ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { downloadFile, jsonRequest, request } from '../api/client'
import { useAuth, useCan } from './useAuth'
import { fr } from '../i18n/fr'
import { personas } from '../mocks/data'
import type { DocumentType, MeResponse, Permission, PurchaseOrder, Receipt, ScannedDocument } from '../types'

const copy = fr.app
type OrderDetail = PurchaseOrder & {
  documents: ScannedDocument[]
  receptions: Receipt[]
}
type ActivityEntry = {
  id: number
  action: string
  utilisateur: string
  date: string
  detail?: string
  bonCommande?: string | null
  bonCommandeId?: number | null
}

type WorkspaceAction = {
  label: string
  description: string
  to: string
  icon: string
  permission?: Permission
}

type RoleWorkspace = {
  title: string
  description: string
  actions: WorkspaceAction[]
}

const roleWorkspaces: Record<string, RoleWorkspace> = {
  'odoo:operateur': {
    title: 'Espace magasin',
    description: 'Enregistrez les bons de livraison et retrouvez vos derniers scans.',
    actions: [
      { label: 'Scanner un BL', description: 'Ajouter une photo ou un fichier', to: '/documents/nouveau', icon: '◉', permission: 'scanner' },
      { label: 'Mes documents', description: 'Consulter les scans enregistrés', to: '/documents', icon: '▧', permission: 'voir_siens' },
      { label: 'Bons de commande', description: 'Retrouver un dossier fournisseur', to: '/bc', icon: '▤', permission: 'voir_siens' },
    ],
  },
  'odoo:comptable': {
    title: 'Espace comptabilité',
    description: 'Suivez les factures, les bons de livraison et les synchronisations ERP.',
    actions: [
      { label: 'Scanner une facture', description: 'Ajouter une facture fournisseur', to: '/documents/nouveau', icon: '＋', permission: 'scanner' },
      { label: 'Documents de l’entreprise', description: 'Filtrer et rapprocher les pièces', to: '/documents', icon: '▧', permission: 'voir_tous' },
      { label: 'Échecs de synchronisation', description: 'Consulter les documents à relancer', to: '/documents?statut=echec', icon: '↻', permission: 'resynchroniser' },
    ],
  },
  'odoo:responsable': {
    title: 'Espace responsable',
    description: 'Supervisez les dossiers d’achat et les opérations documentaires.',
    actions: [
      { label: 'Suivi des commandes', description: 'Repérer les dossiers incomplets', to: '/bc', icon: '▤', permission: 'voir_tous' },
      { label: 'Archives documentaires', description: 'Gérer les BL et les factures', to: '/documents', icon: '▧', permission: 'voir_tous' },
      { label: 'Journal d’audit', description: 'Consulter les actions de l’équipe', to: '/journal', icon: '◷', permission: 'voir_audit' },
    ],
  },
  'odoo:lecteur': {
    title: 'Espace consultation',
    description: 'Consultez les commandes, les documents et leur historique.',
    actions: [
      { label: 'Bons de commande', description: 'Consulter les dossiers d’achat', to: '/bc', icon: '▤', permission: 'voir_tous' },
      { label: 'Documents', description: 'Consulter les BL et factures', to: '/documents', icon: '▧', permission: 'voir_tous' },
      { label: 'Journal d’audit', description: 'Lire l’historique des opérations', to: '/journal', icon: '◷', permission: 'voir_audit' },
    ],
  },
  'odoo:admin': {
    title: 'Administration Odoo',
    description: 'Administrez les comptes et surveillez les connexions aux services.',
    actions: [
      { label: 'Gérer les utilisateurs', description: 'Créer ou désactiver des comptes', to: '/utilisateurs', icon: '♙', permission: 'gerer_utilisateurs' },
      { label: 'État des services', description: 'Contrôler ERP et Google Drive', to: '/connexions', icon: '⌁', permission: 'gerer_utilisateurs' },
      { label: 'Journal d’audit', description: 'Vérifier les actions récentes', to: '/journal', icon: '◷', permission: 'voir_audit' },
    ],
  },
  'urium:magasinier': {
    title: 'Espace magasin',
    description: 'Enregistrez les livraisons et préparez les bons de réception.',
    actions: [
      { label: 'Créer un bon de réception', description: 'Saisir les quantités reçues', to: '/bc', icon: '✓', permission: 'generer_br' },
      { label: 'Scanner un BL', description: 'Ajouter le bon de livraison fournisseur', to: '/documents/nouveau', icon: '◉', permission: 'scanner' },
      { label: 'Mes documents', description: 'Retrouver vos derniers scans', to: '/documents', icon: '▧', permission: 'voir_siens' },
    ],
  },
  'urium:achats': {
    title: 'Espace service achats',
    description: 'Suivez les commandes, les documents fournisseurs et les réceptions.',
    actions: [
      { label: 'Commandes à réceptionner', description: 'Consulter les BC en cours', to: '/bc', icon: '▤', permission: 'voir_tous' },
      { label: 'Ajouter un document', description: 'Scanner un BL ou une facture', to: '/documents/nouveau', icon: '＋', permission: 'scanner' },
      { label: 'Créer un bon de réception', description: 'Enregistrer une réception', to: '/bc', icon: '✓', permission: 'generer_br' },
    ],
  },
  'urium:directeur': {
    title: 'Espace direction',
    description: 'Pilotez les réceptions, les dossiers d’achat et l’activité de l’équipe.',
    actions: [
      { label: 'Suivi des commandes', description: 'Examiner les réceptions en cours', to: '/bc', icon: '▤', permission: 'voir_tous' },
      { label: 'Journal d’audit', description: 'Consulter les opérations de l’équipe', to: '/journal', icon: '◷', permission: 'voir_audit' },
      { label: 'Documents à traiter', description: 'Gérer les scans et synchronisations', to: '/documents', icon: '▧', permission: 'voir_tous' },
    ],
  },
  'urium:admin': {
    title: 'Administration Urium',
    description: 'Administrez les comptes et surveillez les services de l’application.',
    actions: [
      { label: 'Gérer les utilisateurs', description: 'Créer ou désactiver des comptes', to: '/utilisateurs', icon: '♙', permission: 'gerer_utilisateurs' },
      { label: 'État des services', description: 'Contrôler ERP et Google Drive', to: '/connexions', icon: '⌁', permission: 'gerer_utilisateurs' },
      { label: 'Journal d’audit', description: 'Vérifier les actions récentes', to: '/journal', icon: '◷', permission: 'voir_audit' },
    ],
  },
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    non_recu: 'badge-slate',
    partiellement_recu: 'badge-amber',
    entierement_recu: 'badge-green',
    synchronise: 'badge-green',
    en_attente: 'badge-blue',
    echec: 'badge-red',
    brouillon: 'badge-amber',
    valide: 'badge-green',
    annule: 'badge-slate',
    confirme: 'badge-green',
    suspendu: 'badge-amber',
  }
  const label = copy.statuses[status as keyof typeof copy.statuses] ?? status.replaceAll('_', ' ')
  return <span className={`badge ${styles[status] ?? 'badge-slate'}`}>{label}</span>
}

function LoadingState() {
  return (
    <div className="space-y-4" aria-label={copy.loading}>
      <div className="skeleton h-9 w-1/3" />
      <div className="skeleton h-28" />
      <div className="skeleton h-56" />
    </div>
  )
}

function ErrorState({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <section className="state-card" role="alert">
      <div className="state-icon state-icon-error">!</div>
      <div>
        <h2>Une erreur est survenue</h2>
        <p>{error.message}</p>
        <button className="button button-secondary mt-4" onClick={retry}>{copy.retry}</button>
      </div>
    </section>
  )
}

function EmptyState({ title = copy.noResults, detail }: { title?: string; detail?: string }) {
  return (
    <div className="empty-state">
      <span className="empty-state-mark">⌕</span>
      <h3>{title}</h3>
      {detail && <p>{detail}</p>}
    </div>
  )
}

function MetricCard({ label, value, note, icon, tone = 'blue' }: {
  label: string
  value: string | number
  note?: string
  icon: string
  tone?: string
}) {
  return (
    <article className="metric-card">
      <div className={`metric-icon metric-${tone}`}>{icon}</div>
      <div className="min-w-0">
        <p className="metric-label">{label}</p>
        <p className="metric-value">{value}</p>
        {note && <p className="metric-note">{note}</p>}
      </div>
    </article>
  )
}

function PageTitle({ eyebrow, title, description, action }: {
  eyebrow?: string
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="page-title">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {action && <div className="page-title-action">{action}</div>}
    </div>
  )
}

function ConfirmDialog({ open, title, description, confirmLabel, onCancel, onConfirm, busy = false, children }: {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  onCancel: () => void
  onConfirm: () => void
  busy?: boolean
  children?: ReactNode
}) {
  if (!open) return null
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-card" role="alertdialog" aria-modal="true" aria-labelledby="modal-title">
        <span className="modal-mark">!</span>
        <h2 id="modal-title">{title}</h2>
        <p>{description}</p>
        {children}
        <div className="modal-actions">
          <button className="button button-secondary" onClick={onCancel} disabled={busy}>{copy.cancel}</button>
          <button className="button button-primary" onClick={onConfirm} disabled={busy}>
            {busy ? 'Enregistrement…' : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  )
}

function ProtectedRoute({ permission, children }: { permission: Permission; children: ReactNode }) {
  const { loading, me } = useAuth()
  const allowed = useCan(permission)
  if (loading) return <LoadingState />
  if (!me || !allowed) return <Navigate to="/" replace />
  return children
}

const navItems: Array<{ label: string; to: string; icon: string; permission?: Permission; group?: string }> = [
  { label: copy.home, to: '/', icon: '⌂' },
  { label: copy.purchaseOrders, to: '/bc', icon: '▤', group: 'orders' },
  { label: copy.documents, to: '/documents', icon: '▧', group: 'documents' },
  { label: copy.journal, to: '/journal', icon: '◷', permission: 'voir_audit', group: 'activity' },
  { label: copy.users, to: '/utilisateurs', icon: '♙', permission: 'gerer_utilisateurs', group: 'users' },
  { label: copy.connections, to: '/connexions', icon: '⌁', permission: 'gerer_utilisateurs' },
]

function AppShell({ children }: { children: ReactNode }) {
  const { me } = useAuth()
  const canScan = useCan('scanner')
  const canReadOwn = useCan('voir_siens')
  const canReadAll = useCan('voir_tous')
  const canRead = canReadOwn || canReadAll
  const canCreateReceipt = useCan('generer_br')
  const [online, setOnline] = useState(navigator.onLine)
  const [showMore, setShowMore] = useState(false)
  const visibleNav = navItems.filter((item) => {
    if (item.permission && !me?.permissions.includes(item.permission)) return false
    if (item.group === 'orders' || item.group === 'documents') return canRead || canCreateReceipt || canScan
    return true
  }).map((item) => item.group === 'documents'
    ? { ...item, label: canReadAll ? copy.documents : copy.myDocuments }
    : item)
  const mobileNavItems = [
    visibleNav.find((item) => item.to === '/'),
    visibleNav.find((item) => item.to === '/bc'),
    canScan ? { label: 'Scanner', to: '/documents/nouveau', icon: '◉' } : undefined,
    visibleNav.find((item) => item.group === 'documents'),
    ...visibleNav.filter((item) => item.group === 'activity' || item.group === 'users' || item.to === '/connexions'),
  ].filter((item): item is NonNullable<typeof item> => Boolean(item))
  const mobileNav = mobileNavItems.slice(0, 4)
  const mobileMore = mobileNavItems.slice(4)

  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [])

  return (
    <div className="app-shell" style={{ '--brand': me?.entreprise.couleur ?? '#0e7490' } as CSSProperties}>
      <aside className="sidebar">
        <Link to="/" className="brand-lockup" aria-label={copy.name}>
          <span className="brand-symbol">{me?.entreprise.logo ?? 'AC'}</span>
          <span><strong>{copy.name}</strong><small>{copy.subtitle}</small></span>
        </Link>
        <div className="sidebar-caption">ESPACE DE TRAVAIL</div>
        <nav className="side-nav" aria-label="Navigation principale">
          {visibleNav.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-link ${isActive ? 'nav-active' : ''}`}>
              <span className="nav-icon">{item.icon}</span>{item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="company-avatar">{me?.entreprise.logo}</div>
          <span><strong>{me?.entreprise.nom}</strong><small>{me?.entreprise.erp_type.toUpperCase()} · Connecté</small></span>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="topbar-company">
            <span className="company-avatar">{me?.entreprise.logo}</span>
            <span className="topbar-company-name">{me?.entreprise.nom}</span>
            {import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === 'true' && <span className="environment-tag">ENVIRONNEMENT DE DÉMO</span>}
          </div>
          <div className="topbar-actions">
            {import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === 'true' && (
              <label className="persona-switcher">
                <span>{copy.switchProfile}</span>
                <select
                  aria-label={copy.switchProfile}
                  value={personas.find((item) => item.me.utilisateur.role === me?.utilisateur.role && item.me.entreprise.code === me?.entreprise.code)?.id}
                  onChange={(event) => {
                    localStorage.setItem('achats:persona', event.target.value)
                    window.location.reload()
                  }}
                >
                  {personas.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
            <Link className="profile-chip" to="/profil">
              <span className="profile-avatar">{me?.utilisateur.nom.split(' ').map((part) => part[0]).slice(0, 2).join('')}</span>
              <span className="profile-name">{me?.utilisateur.nom}</span>
              <span className="profile-chevron">⌄</span>
            </Link>
          </div>
        </header>
        {!online && <div className="offline-banner" role="status">{copy.offline}</div>}
        <main className="main-content">{children}</main>
        <nav className="mobile-nav" aria-label="Navigation mobile">
          {mobileNav.map((item) => (
            <Link key={item.to} to={item.to} className="mobile-nav-link">
              <span>{item.icon}</span>{item.label}
            </Link>
          ))}
          {mobileMore.length > 0 && <button className="mobile-nav-link" aria-expanded={showMore} onClick={() => setShowMore((visible) => !visible)}><span>⋯</span>Plus</button>}
          {showMore && mobileMore.length > 0 && <div className="mobile-more-menu">{mobileMore.map((item) => <Link key={item.to} to={item.to} onClick={() => setShowMore(false)}><span>{item.icon}</span>{item.label}</Link>)}</div>}
        </nav>
      </div>
    </div>
  )
}

function HomePage() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const ordersQuery = useQuery({ queryKey: ['orders'], queryFn: () => request<PurchaseOrder[]>('/api/bc') })
  const scansQuery = useQuery({ queryKey: ['scans'], queryFn: () => request<ScannedDocument[]>('/api/scans') })
  const dashboardQuery = useQuery({ queryKey: ['dashboard'], queryFn: () => request<{ scansParJour: number[]; labelsScans: string[]; dossiersIncomplets: number; echecs: number; brDuJour: number; date: string; dateIso: string }>('/api/tableau-de-bord') })
  const canScan = useCan('scanner')
  const canReceive = useCan('generer_br')
  const canSeeAll = useCan('voir_tous')
  const canAudit = useCan('voir_audit')
  const workspace = me
    ? roleWorkspaces[`${me.entreprise.erp_type}:${me.utilisateur.role}`]
    : undefined
  const workspaceActions = workspace?.actions.filter(
    (action) => !action.permission || me?.permissions.includes(action.permission),
  ) ?? []
  const orders = ordersQuery.data ?? []
  const scans = scansQuery.data ?? []
  const incomplete = dashboardQuery.data?.dossiersIncomplets ?? 0
  const errors = dashboardQuery.data?.echecs ?? 0
  const erpIsUrium = me?.entreprise.erp_type === 'urium'
  const fieldMode = me?.utilisateur.role === 'operateur' || me?.utilisateur.role === 'magasinier'

  return (
    <div className="page-stack">
      <PageTitle
        eyebrow={workspace?.title ?? dashboardQuery.data?.date ?? 'ESPACE DE TRAVAIL'}
        title={`Bonjour ${me?.utilisateur.nom.split(' ')[0] ?? ''} 👋`}
        description={workspace?.description ?? (erpIsUrium ? 'Voici les réceptions et dossiers qui demandent votre attention.' : 'Retrouvez en un coup d’œil les dossiers et documents de votre activité.')}
        action={canScan ? <Link className="button button-primary" to="/documents/nouveau"><span>＋</span>{copy.newScan}</Link> : undefined}
      />
      {ordersQuery.isPending || scansQuery.isPending || dashboardQuery.isPending ? <LoadingState /> : ordersQuery.error ? <ErrorState error={ordersQuery.error} retry={() => void queryClient.invalidateQueries({ queryKey: ['orders'] })} /> : scansQuery.error ? <ErrorState error={scansQuery.error} retry={() => void queryClient.invalidateQueries({ queryKey: ['scans'] })} /> : dashboardQuery.error ? <ErrorState error={dashboardQuery.error} retry={() => void queryClient.invalidateQueries({ queryKey: ['dashboard'] })} /> : (
        <>
          {workspaceActions.length > 0 && (
            <section className="workspace-actions" aria-label="Raccourcis de votre espace">
              {workspaceActions.map((action) => (
                <Link className="workspace-action panel" to={action.to} key={action.label}>
                  <span className="workspace-action-icon">{action.icon}</span>
                  <span className="workspace-action-copy"><strong>{action.label}</strong><small>{action.description}</small></span>
                  <span className="workspace-action-arrow" aria-hidden="true">→</span>
                </Link>
              ))}
            </section>
          )}
          {fieldMode && (
            <section className="field-hero panel">
              <span className="field-hero-icon">▧</span>
              <div><p className="eyebrow">ESPACE TERRAIN</p><h2>Un document à enregistrer ?</h2><p>Photographiez le bon de livraison et rattachez-le au bon de commande.</p></div>
              <Link className="button button-primary" to="/documents/nouveau">{copy.scanBl} <span>→</span></Link>
            </section>
          )}
          {!fieldMode && <section className="metrics-grid">
            {erpIsUrium ? (
              <>
                <MetricCard label={copy.kpis.incomplete} value={incomplete} note="À compléter cette semaine" icon="▤" tone="blue" />
                <MetricCard label={copy.kpis.receiptToday} value={dashboardQuery.data?.brDuJour ?? 0} note="Réceptions enregistrées" icon="✓" tone="violet" />
                <MetricCard label={copy.kpis.failure} value={errors} note="À traiter" icon="↻" tone="rose" />
                <MetricCard label={copy.kpis.totalOrders} value={orders.length} note="Commandes en cours" icon="⌑" tone="green" />
              </>
            ) : (
              <>
                <MetricCard label={copy.kpis.withoutInvoice} value={orders.filter((order) => order.factures === 0).length} note="À rapprocher" icon="▤" tone="blue" />
                <MetricCard label={copy.kpis.failure} value={errors} note="À synchroniser" icon="↻" tone="rose" />
                <MetricCard label={copy.kpis.today} value={scans.filter((scan) => scan.date.slice(0, 10) === dashboardQuery.data?.dateIso).length} note="Documents enregistrés" icon="↗" tone="violet" />
                <MetricCard label={copy.kpis.incomplete} value={incomplete} note="Dossiers à suivre" icon="⌑" tone="green" />
              </>
            )}
          </section>}
          {fieldMode ? <section className="panel recent-panel"><div className="panel-heading"><div><p className="eyebrow">DERNIÈRE ACTIVITÉ</p><h2>{copy.recentDocuments}</h2></div><Link className="text-link" to="/documents">{copy.myDocuments} →</Link></div>{scans.length === 0 ? <EmptyState title="Aucun scan récent" detail="Vos documents ajoutés apparaîtront ici." /> : <div className="recent-list">{scans.slice(0, 5).map((scan) => <Link to={`/documents/${scan.id}`} className="recent-row" key={scan.id}><span className="document-type-icon">BL</span><span className="recent-main"><strong>{scan.numero}</strong><small>{scan.fournisseur}</small></span><StatusBadge status={scan.statut} /></Link>)}</div>}</section> : <section className="home-grid">
            <article className="panel orders-panel">
              <div className="panel-heading">
                <div><p className="eyebrow">SUIVI DES ACHATS</p><h2>{erpIsUrium ? copy.ordersToReceive : 'Bons de commande récents'}</h2></div>
                <Link className="text-link" to="/bc">Tout voir <span>→</span></Link>
              </div>
              {orders.length === 0 ? <EmptyState /> : (
                <div className="order-list">
                  {orders.filter((order) => !erpIsUrium || order.statutReception !== 'entierement_recu').slice(0, 4).map((order) => (
                    <Link to={`/bc/${order.id}`} className="order-row" key={order.id}>
                      <span className="order-icon">▤</span>
                      <span className="order-row-main"><strong>{order.reference}</strong><small>{order.fournisseur} · {order.date}</small></span>
                      <span className="order-row-status"><StatusBadge status={order.statutReception} /><small>{order.completude}% complété</small></span>
                    </Link>
                  ))}
                </div>
              )}
              {canReceive && erpIsUrium && <Link className="button button-soft mt-4 w-full" to="/bc">{copy.createReceipt} <span>→</span></Link>}
            </article>
            <article className="panel recent-panel">
              <div className="panel-heading">
                <div><p className="eyebrow">DERNIÈRE ACTIVITÉ</p><h2>{copy.recentDocuments}</h2></div>
                <Link className="text-link" to="/documents">{canSeeAll ? 'Tout voir →' : 'Mes documents →'}</Link>
              </div>
              {scans.length === 0 ? <EmptyState /> : (
                <div className="recent-list">
                  {scans.slice(0, 4).map((scan) => (
                    <Link to={`/documents/${scan.id}`} className="recent-row" key={scan.id}>
                      <span className={`document-type-icon ${scan.type === 'FACTURE' ? 'invoice-icon' : ''}`}>{scan.type === 'BL' ? 'BL' : 'FA'}</span>
                      <span className="recent-main"><strong>{scan.numero}</strong><small>{scan.fournisseur}</small></span>
                      <StatusBadge status={scan.statut} />
                    </Link>
                  ))}
                </div>
              )}
            </article>
          </section>}
          {canAudit && dashboardQuery.data && (
            <section className="panel activity-dashboard">
              <div className="panel-heading"><div><p className="eyebrow">ANALYSE D’ACTIVITÉ</p><h2>Scans des 7 derniers jours</h2></div><Link className="text-link" to="/journal">Ouvrir le journal →</Link></div>
              <div className="chart-bars" role="img" aria-label="Graphique des scans par jour">{dashboardQuery.data.scansParJour.map((value, index) => <div className="chart-column" key={dashboardQuery.data.labelsScans[index]}><span className="chart-value">{value}</span><div className="chart-bar-track"><i style={{ height: `${Math.min(100, value * 4)}%` }} /></div><small>{dashboardQuery.data.labelsScans[index]}</small></div>)}</div>
              <div className="chart-summary"><span><i className="summary-dot summary-dot-amber" />{incomplete} dossiers incomplets</span><span><i className="summary-dot summary-dot-red" />{errors} synchronisations en échec</span></div>
            </section>
          )}
          {canAudit && <ActivityPreview />}
        </>
      )}
    </div>
  )
}

function ActivityPreview() {
  const query = useQuery({ queryKey: ['journal'], queryFn: () => request<ActivityEntry[]>('/api/journal') })
  return (
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">TRAÇABILITÉ</p><h2>Activité récente</h2></div><Link className="text-link" to="/journal">Ouvrir le journal →</Link></div>
      {query.isPending ? <LoadingState /> : query.error ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : <ActivityRows rows={query.data?.slice(0, 3) ?? []} />}
    </section>
  )
}

function ActivityRows({ rows }: { rows: ActivityEntry[] }) {
  return (
    <div className="activity-list">
      {rows.map((row) => <div className="activity-row" key={row.id}><span className="activity-dot" /><span><strong>{row.action}</strong><small>{row.utilisateur}</small>{row.detail && <small>{row.detail}</small>}{row.bonCommande && row.bonCommandeId && <Link className="small-link" to={`/bc/${row.bonCommandeId}`}>{row.bonCommande}</Link>}</span><time dateTime={row.date}>{new Date(row.date).toLocaleString('fr-FR')}</time></div>)}
    </div>
  )
}

function OrdersPage() {
  const [search, setSearch] = useState('')
  const [incompleteOnly, setIncompleteOnly] = useState(false)
  const [supplier, setSupplier] = useState('')
  const [period, setPeriod] = useState('')
  const [page, setPage] = useState(0)
  const query = useQuery({
    queryKey: ['orders', search, incompleteOnly, supplier, period],
    queryFn: () => request<PurchaseOrder[]>(`/api/bc?recherche=${encodeURIComponent(search)}&incomplets=${incompleteOnly}&fournisseur=${encodeURIComponent(supplier)}&periode=${period}`),
  })
  const suppliers = [...new Set((query.data ?? []).map((order) => order.fournisseur))]
  const pageSize = 10
  const pageCount = Math.max(1, Math.ceil((query.data?.length ?? 0) / pageSize))
  const pageOrders = query.data?.slice(page * pageSize, (page + 1) * pageSize) ?? []

  return (
    <div className="page-stack">
      <PageTitle eyebrow="ACHATS · ERP" title={copy.purchaseOrders} description="Recherchez une commande et suivez la réception de ses documents." />
      <section className="filter-bar">
        <label className="search-control"><span>⌕</span><input aria-label={copy.search} value={search} onChange={(event) => { setSearch(event.target.value); setPage(0) }} placeholder={copy.searchPlaceholder} /></label>
        <label className="select-control"><span className="sr-only">Fournisseur</span><select value={supplier} onChange={(event) => { setSupplier(event.target.value); setPage(0) }}><option value="">Tous les fournisseurs</option>{suppliers.map((name) => <option key={name}>{name}</option>)}</select></label>
        <label className="select-control"><span className="sr-only">Période</span><select value={period} onChange={(event) => { setPeriod(event.target.value); setPage(0) }}><option value="">Toutes les périodes</option><option value="30">30 derniers jours</option><option value="90">90 derniers jours</option><option value="365">12 derniers mois</option></select></label>
        <label className="check-control"><input type="checkbox" checked={incompleteOnly} onChange={(event) => { setIncompleteOnly(event.target.checked); setPage(0) }} /><span>{copy.incomplete}</span></label>
      </section>
      <section className="panel table-panel">
        <div className="panel-heading"><div><p className="eyebrow">{query.data?.length ?? 0} DOSSIERS</p><h2>Résultats de recherche</h2></div><span className="small-muted">Mis à jour à l’instant</span></div>
        {query.isPending ? <LoadingState /> : query.error ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : query.data?.length ? (
          <>
            <div className="table-scroll">
              <table className="data-table card-table">
                <thead><tr><th>Référence</th><th>Fournisseur</th><th>Date</th><th>Réception</th><th>Complétude</th><th><span className="sr-only">Ouvrir</span></th></tr></thead>
                <tbody>{pageOrders.map((order) => (
                  <tr key={order.id}>
                    <td data-label="Référence"><Link className="table-reference" to={`/bc/${order.id}`}>{order.reference}</Link></td>
                    <td data-label="Fournisseur">{order.fournisseur}</td><td data-label="Date">{order.date}</td><td data-label="Réception"><StatusBadge status={order.statutReception} /></td>
                    <td data-label="Complétude"><div className="completion-cell"><span className="progress-track"><span style={{ width: `${order.completude}%` }} /></span><small>{order.completude}%</small></div></td>
                    <td data-label="Ouvrir"><Link className="icon-button" aria-label={`${copy.openFolder} ${order.reference}`} to={`/bc/${order.id}`}>↗</Link></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <div className="table-footer"><span>Affichage de {page * pageSize + 1} à {Math.min((page + 1) * pageSize, query.data.length)} sur {query.data.length} dossiers</span><div><button className="pager-button" aria-label="Page précédente" disabled={page === 0} onClick={() => setPage((current) => current - 1)}>‹</button><button className="pager-button pager-current">{page + 1} / {pageCount}</button><button className="pager-button" aria-label="Page suivante" disabled={page + 1 >= pageCount} onClick={() => setPage((current) => current + 1)}>›</button></div></div>
          </>
        ) : <EmptyState detail="Essayez de modifier vos filtres ou votre recherche." />}
      </section>
    </div>
  )
}

function OrderDetailPage() {
  const { id } = useParams()
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState('Lignes')
  const query = useQuery({ queryKey: ['order', id], queryFn: () => request<OrderDetail>(`/api/bc/${id}`) })
  const canScan = useCan('scanner')
  const canGenerateReceipt = useCan('generer_br') && me?.entreprise.erp_type === 'urium'
  if (query.isPending) return <LoadingState />
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  const order = query.data
  if (!order) return <EmptyState title="Bon de commande introuvable" />
  const tabs = ['Lignes', 'BL', 'BR', 'Factures', 'Historique']
  const linkedDocuments = tab === 'BL' ? order.documents.filter((item) => item.type === 'BL')
    : tab === 'Factures' ? order.documents.filter((item) => item.type === 'FACTURE') : []

  return (
    <div className="page-stack">
      <Link to="/bc" className="back-link">← {copy.backToOrders}</Link>
      <section className="order-hero panel">
        <div className="order-hero-main">
          <span className="order-icon order-icon-large">▤</span>
          <div><p className="eyebrow">DOSSIER D’ACHAT</p><h1>{order.reference}</h1><p>{order.fournisseur} <span className="separator-dot">·</span> {order.date}</p></div>
        </div>
        <div className="order-hero-actions">
          <StatusBadge status={order.statutReception} />
          {canScan && <Link to={`/documents/nouveau?bc=${order.id}`} className="button button-secondary">＋ Ajouter un document</Link>}
          {canGenerateReceipt && <Link to={`/bc/${order.id}/br`} className="button button-primary">＋ {copy.createReceipt}</Link>}
        </div>
        <div className="order-facts">
          <div><span>Montant total</span><strong>{new Intl.NumberFormat('fr-MA', { style: 'currency', currency: order.devise, maximumFractionDigits: 0 }).format(order.montant)}</strong></div>
          <div><span>Complétude</span><strong>{order.completude}%</strong><span className="progress-track"><span style={{ width: `${order.completude}%` }} /></span></div>
          <div><span>Documents liés</span><strong>{order.bl + order.br + order.factures} <small>documents</small></strong></div>
        </div>
      </section>
      <section className="panel detail-panel">
        <div className="tabs" role="tablist">{tabs.map((item) => <button key={item} role="tab" aria-selected={tab === item} className={tab === item ? 'tab-active' : ''} onClick={() => setTab(item)}>{item}{item === 'BL' ? <span>{order.bl}</span> : item === 'BR' ? <span>{order.br}</span> : item === 'Factures' ? <span>{order.factures}</span> : null}</button>)}</div>
        {tab === 'Lignes' ? (
          <div className="table-scroll"><table className="data-table"><thead><tr><th>Article</th><th>Commandé</th><th>Déjà reçu</th><th>Reste à recevoir</th></tr></thead>
            <tbody>{order.lignes.map((line) => <tr key={line.article}><td className="table-reference">{line.article}</td><td>{line.commande} {line.unite}</td><td>{line.recue} {line.unite}</td><td>{line.commande - line.recue} {line.unite}</td></tr>)}</tbody></table></div>
        ) : tab === 'BR' && me?.entreprise.erp_type === 'odoo' ? (
          <EmptyState title="Bons de réception en lecture seule" detail="Les BR sont synchronisés depuis Odoo et ne peuvent pas être modifiés ici." />
        ) : tab === 'BR' ? (
          <ReceiptList order={order} onUpdated={() => void queryClient.invalidateQueries({ queryKey: ['order', id] })} />
        ) : tab === 'Historique' ? <ActivityPreview /> : (
          linkedDocuments.length ? <div className="recent-list">{linkedDocuments.map((doc) => <Link className="recent-row" to={`/documents/${doc.id}`} key={doc.id}><span className="document-type-icon">{doc.type}</span><span className="recent-main"><strong>{doc.numero}</strong><small>{doc.fournisseur}</small></span><StatusBadge status={doc.statut} /></Link>)}</div> : <EmptyState title={`Aucun document ${tab === 'BL' ? 'de livraison' : 'de facture'} lié`} detail="Ajoutez un scan pour compléter ce dossier." />
        )}
      </section>
    </div>
  )
}

function ReceiptList({ order, onUpdated }: { order: OrderDetail; onUpdated: () => void }) {
  const canCancel = useCan('annuler_br')
  const [receiptToCancel, setReceiptToCancel] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const [message, setMessage] = useState('')
  const cancel = useMutation({
    mutationFn: (id: number) => request<Receipt>(`/api/br/${id}/annuler`, jsonRequest('POST', { motif: reason })),
    onSuccess: () => { setMessage('Le bon de réception a été annulé.'); setReceiptToCancel(null); setReason(''); onUpdated() },
    onError: (error: Error) => setMessage(error.message),
  })
  return (
    <>
      {message && <p className="inline-notice" role="status">{message}</p>}
      {order.receptions.length === 0 ? <EmptyState title="Aucun bon de réception" detail="Les réceptions enregistrées apparaîtront ici." /> : (
        <div className="recent-list">{order.receptions.map((receipt) => <div className="recent-row" key={receipt.id}><span className="document-type-icon receipt-icon">BR</span><span className="recent-main"><strong>{receipt.reference}</strong><small>{receipt.lignes.length} ligne(s) · Réception</small></span><StatusBadge status={receipt.statut} />{canCancel && receipt.statut === 'valide' && <button className="button button-quiet" onClick={() => setReceiptToCancel(receipt.id)}>Annuler</button>}</div>)}</div>
      )}
      <ConfirmDialog open={receiptToCancel !== null} title="Annuler ce bon de réception ?" description="Cette action sera inscrite au journal. Le motif est obligatoire." confirmLabel="Confirmer l’annulation" onCancel={() => setReceiptToCancel(null)} onConfirm={() => receiptToCancel && cancel.mutate(receiptToCancel)} busy={cancel.isPending}>
        <label className="field-label mt-4">Motif d’annulation<input className="text-input" value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      </ConfirmDialog>
    </>
  )
}

function DocumentsPage() {
  const canSeeAll = useCan('voir_tous')
  const canSeeOwn = useCan('voir_siens')
  const canScan = useCan('scanner')
  const canDelete = useCan('supprimer')
  const canReplace = useCan('remplacer')
  const canResync = useCan('resynchroniser')
  const [search, setSearch] = useState('')
  const [type, setType] = useState('')
  const location = useLocation()
  const [status, setStatus] = useState(() => new URLSearchParams(location.search).get('statut') ?? '')
  const [period, setPeriod] = useState('')
  const [page, setPage] = useState(0)
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['scans', search, type, status, period],
    queryFn: () => request<ScannedDocument[]>(`/api/scans?recherche=${encodeURIComponent(search)}&type=${encodeURIComponent(type)}&statut=${encodeURIComponent(status)}&periode=${period}`),
  })
  const pageSize = 10
  const pageCount = Math.max(1, Math.ceil((query.data?.length ?? 0) / pageSize))
  const pageDocuments = query.data?.slice(page * pageSize, (page + 1) * pageSize) ?? []
  const [message, setMessage] = useState('')
  const action = useMutation({
    mutationFn: ({ id, method }: { id: number; method: 'DELETE' | 'PATCH' | 'POST' }) =>
      request(`/api/scans/${id}${method === 'POST' ? '/resynchroniser' : ''}`, { method }),
    onSuccess: () => { setMessage('Action effectuée.'); void queryClient.invalidateQueries({ queryKey: ['scans'] }) },
    onError: (error: Error) => setMessage(error.message),
  })

  if (!canSeeAll && !canSeeOwn && !canScan) return <Navigate to="/" replace />
  return (
    <div className="page-stack">
      <PageTitle eyebrow="ARCHIVES DOCUMENTAIRES" title={canSeeAll ? copy.allDocuments : copy.myDocuments} description="Retrouvez les bons de livraison et factures associés aux commandes." action={canScan ? <Link className="button button-primary" to="/documents/nouveau">＋ {copy.newScan}</Link> : undefined} />
      <section className="filter-bar">
        <label className="search-control"><span>⌕</span><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(0) }} placeholder={copy.searchPlaceholder} /></label>
        <label className="select-control"><span className="sr-only">Type de document</span><select value={type} onChange={(event) => { setType(event.target.value); setPage(0) }}><option value="">Tous les types</option><option value="BL">Bon de livraison</option><option value="FACTURE">Facture</option></select></label>
        <label className="select-control"><span className="sr-only">Statut de synchronisation</span><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(0) }}><option value="">Tous les statuts</option><option value="synchronise">Synchronisé</option><option value="en_attente">En attente</option><option value="echec">Échec</option></select></label>
        <label className="select-control"><span className="sr-only">Période des documents</span><select value={period} onChange={(event) => { setPeriod(event.target.value); setPage(0) }}><option value="">Toutes les périodes</option><option value="30">30 derniers jours</option><option value="90">90 derniers jours</option><option value="365">12 derniers mois</option></select></label>
        {canSeeAll && <button className="button button-secondary" onClick={() => {
          const csv = ['Type;Numéro;Fournisseur;BC;Statut', ...(query.data ?? []).map((item) => `${item.type};${item.numero};${item.fournisseur};${item.bc.join(', ')};${item.statut}`)].join('\n')
          const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
          const link = document.createElement('a')
          link.href = url
          link.download = 'documents-achats.csv'
          link.click()
          URL.revokeObjectURL(url)
        }}>↓ Exporter CSV</button>}
      </section>
      {message && <p className="inline-notice" role="status">{message}</p>}
      <section className="panel table-panel">
        <div className="panel-heading"><div><p className="eyebrow">{query.data?.length ?? 0} DOCUMENTS</p><h2>Liste des scans</h2></div></div>
        {query.isPending ? <LoadingState /> : query.error ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : query.data?.length ? (
          <div className="table-scroll"><table className="data-table card-table"><thead><tr><th>Document</th><th>BC lié(s)</th><th>Ajouté par</th><th>Date</th><th>Synchronisation</th><th>Actions</th></tr></thead>
            <tbody>{pageDocuments.map((item) => <tr key={item.id}>
              <td data-label="Document"><Link className="table-reference" to={`/documents/${item.id}`}>{item.numero}</Link><small className="table-subtext">{item.type} · {item.fournisseur}</small></td>
              <td data-label="BC lié(s)">{item.bc.map((bc, index) => <Link className="small-link" key={bc} to={`/bc/${item.bcIds?.[index] ?? bc.slice(-4)}`}>{bc}</Link>)}</td>
              <td data-label="Ajouté par">{item.auteur}</td><td data-label="Date">{new Date(item.date).toLocaleDateString('fr-FR')}</td><td data-label="Synchronisation"><StatusBadge status={item.statut} /></td>
              <td data-label="Actions"><div className="table-actions">
                {canResync && item.statut === 'echec' && <button className="button button-quiet" onClick={() => action.mutate({ id: item.id, method: 'POST' })}>↻ Resynchroniser</button>}
                {canReplace && <Link className="icon-button" aria-label={`Ouvrir ${item.numero} pour le remplacer`} to={`/documents/${item.id}`}>↻</Link>}
                {canDelete && <button className="icon-button icon-danger" aria-label={`Supprimer ${item.numero}`} onClick={() => window.confirm(`Supprimer ${item.numero} ?`) && action.mutate({ id: item.id, method: 'DELETE' })}>×</button>}
              </div></td>
            </tr>)}</tbody></table></div>
        ) : <EmptyState title="Aucun document trouvé" detail="Modifiez les filtres ou ajoutez un document à un dossier." />}
        {query.data?.length ? <div className="table-footer"><span>Affichage de {page * pageSize + 1} à {Math.min((page + 1) * pageSize, query.data.length)} sur {query.data.length} documents</span><div><button className="pager-button" aria-label="Page précédente" disabled={page === 0} onClick={() => setPage((current) => current - 1)}>‹</button><button className="pager-button pager-current">{page + 1} / {pageCount}</button><button className="pager-button" aria-label="Page suivante" disabled={page + 1 >= pageCount} onClick={() => setPage((current) => current + 1)}>›</button></div></div> : null}
      </section>
    </div>
  )
}

interface ScanFormValues { type: DocumentType; numero_document: string }

async function prepareUpload(files: File[]): Promise<File> {
  if (files.length === 1 && files[0].type === 'application/pdf') return files[0]
  const { PDFDocument } = await import('pdf-lib')
  const pdf = await PDFDocument.create()
  for (const file of files) {
    if (!file.type.startsWith('image/')) throw new Error('Associez un PDF seul ou des images uniquement.')
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, 2000 / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    const context = canvas.getContext('2d')
    if (!context) throw new Error('La compression de cette image est impossible.')
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()
    const imageBlob = await new Promise<Blob>((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('La compression de cette image a échoué.')), 'image/jpeg', 0.82))
    const image = await pdf.embedJpg(await imageBlob.arrayBuffer())
    const page = pdf.addPage([image.width, image.height])
    page.drawImage(image, { x: 0, y: 0, width: image.width, height: image.height })
  }
  const bytes = await pdf.save()
  const output = new ArrayBuffer(bytes.byteLength)
  new Uint8Array(output).set(bytes)
  return new File([output], 'document-scan.pdf', { type: 'application/pdf' })
}

function ScanFormPage() {
  const { me } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const params = new URLSearchParams(window.location.search)
  const [selectedOrders, setSelectedOrders] = useState<number[]>(params.get('bc') ? [Number(params.get('bc'))] : [])
  const [files, setFiles] = useState<File[]>([])
  const [errorMessage, setErrorMessage] = useState('')
  const [orderSearch, setOrderSearch] = useState('')
  const [numberValue, setNumberValue] = useState('')
  const [cropIndex, setCropIndex] = useState<number | null>(null)
  const [cropMargin, setCropMargin] = useState(5)
  const [cropPreview, setCropPreview] = useState('')
  const [success, setSuccess] = useState<ScannedDocument | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const ordersQuery = useQuery({ queryKey: ['orders'], queryFn: () => request<PurchaseOrder[]>('/api/bc') })
  const scansQuery = useQuery({ queryKey: ['scans'], queryFn: () => request<ScannedDocument[]>('/api/scans') })
  const { register, handleSubmit, formState: { errors } } = useForm<ScanFormValues>()
  const documentNumber = numberValue.trim().toLocaleLowerCase('fr')
  const duplicateNumber = Boolean(documentNumber && scansQuery.data?.some((scan) => scan.numero.toLocaleLowerCase('fr') === documentNumber))
  const cropFile = cropIndex === null ? undefined : files[cropIndex]
  const numberRegistration = register('numero_document', { required: copy.numberRequired })
  const availableOrders = (ordersQuery.data ?? []).filter((order) =>
    `${order.reference} ${order.fournisseur}`.toLocaleLowerCase('fr').includes(orderSearch.toLocaleLowerCase('fr')),
  )

  useEffect(() => {
    if (!cropFile) return
    const url = URL.createObjectURL(cropFile)
    setCropPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [cropFile])
  const upload = useMutation({
    mutationFn: async (values: ScanFormValues) => {
      const uploadFile = await prepareUpload(files)
      const formData = new FormData()
      formData.set('fichier', uploadFile)
      formData.set('type', values.type)
      formData.set('numero_document', values.numero_document.trim())
      formData.set('ids_bc', JSON.stringify(selectedOrders))
      return request<ScannedDocument>('/api/scans', { method: 'POST', body: formData })
    },
    onSuccess: (document) => {
      setSuccess(document)
      setErrorMessage('')
      void queryClient.invalidateQueries({ queryKey: ['scans'] })
    },
    onError: (error: Error) => setErrorMessage(error.message),
  })

  const addFiles = (selected: FileList | null) => {
    if (!selected) return
    const incoming = Array.from(selected)
    const invalid = incoming.find((file) => !['application/pdf', 'image/jpeg', 'image/png', 'image/webp'].includes(file.type))
    if (invalid) { setErrorMessage('Format refusé. Choisissez un fichier JPEG, PNG ou PDF.'); return }
    if (incoming.some((file) => file.size > 20 * 1024 * 1024)) { setErrorMessage('Fichier trop lourd. La taille maximale est de 20 Mo par page.'); return }
    if (incoming.some((file) => file.type === 'application/pdf') && (incoming.length > 1 || files.length > 0)) { setErrorMessage('Un PDF ne peut pas être combiné avec d’autres pages.'); return }
    setFiles((current) => [...current, ...incoming])
    setErrorMessage('')
  }

  const applyCrop = async () => {
    if (cropIndex === null || !cropFile) return
    try {
      const bitmap = await createImageBitmap(cropFile)
      const marginX = Math.round(bitmap.width * cropMargin / 100)
      const marginY = Math.round(bitmap.height * cropMargin / 100)
      const width = bitmap.width - marginX * 2
      const height = bitmap.height - marginY * 2
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Le recadrage de cette image est impossible.')
      context.drawImage(bitmap, marginX, marginY, width, height, 0, 0, width, height)
      bitmap.close()
      const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob((result) => result ? resolve(result) : reject(new Error('Le recadrage de cette image a échoué.')), 'image/jpeg', 0.9))
      const cropped = new File([blob], cropFile.name.replace(/\.[^.]+$/, '-recadre.jpg'), { type: 'image/jpeg' })
      setFiles((current) => current.map((file, index) => index === cropIndex ? cropped : file))
      setCropIndex(null)
      setErrorMessage('')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Le recadrage de cette image a échoué.')
    }
  }

  const submit = handleSubmit((values) => {
    if (duplicateNumber) { setErrorMessage('Ce numéro de document existe déjà.'); return }
    if (selectedOrders.length === 0) { setErrorMessage(copy.orderRequired); return }
    if (files.length === 0) { setErrorMessage(copy.fileRequired); return }
    upload.mutate(values)
  })

  if (success) return (
    <div className="page-stack">
      <section className="success-card">
        <span className="success-check">✓</span><p className="eyebrow">DOCUMENT AJOUTÉ</p><h1>{copy.documentAdded}</h1>
        <p>{success.numero} · {success.type}</p><StatusBadge status={success.statut} />
        <div className="success-actions"><button className="button button-secondary" onClick={() => navigate(`/bc/${selectedOrders[0]}`)}>Ouvrir le dossier BC →</button><button className="button button-primary" onClick={() => { setSuccess(null); setFiles([]); setSelectedOrders([]) }}>Ajouter un autre document</button></div>
      </section>
    </div>
  )

  return (
    <div className="page-stack">
      <Link to="/bc" className="back-link">← Retour aux commandes</Link>
      <PageTitle eyebrow="NOUVEAU DOCUMENT · ÉTAPE 1 SUR 3" title={copy.newScan} description="Associez le document à un ou plusieurs bons de commande." />
      <div className="stepper"><div className="step step-current"><span>1</span>Informations</div><i /><div className="step"><span>2</span>Fichier</div><i /><div className="step"><span>3</span>Envoi</div></div>
      <form className="form-layout" onSubmit={(event) => void submit(event)}>
        <section className="panel form-panel">
          <div className="form-section-heading"><span className="step-number">01</span><div><h2>Informations du document</h2><p>Le numéro du document est nécessaire pour le retrouver rapidement.</p></div></div>
          <div className="form-fields-grid">
            <label className="field-label">Type de document <select className="text-input" {...register('type', { required: copy.typeRequired })}><option value="">Sélectionner un type…</option>{me?.types_scannables.map((item) => <option key={item} value={item}>{item === 'BL' ? 'Bon de livraison (BL)' : 'Facture fournisseur'}</option>)}</select>{errors.type && <small className="field-error">{errors.type.message}</small>}</label>
            <label className="field-label">Numéro du document <input className="text-input" placeholder="Ex. BL-2026-0042" {...numberRegistration} onChange={(event) => { void numberRegistration.onChange(event); setNumberValue(event.target.value) }} />{errors.numero_document && <small className="field-error">{errors.numero_document.message}</small>}{duplicateNumber && <small className="field-error" role="alert">Ce numéro de document existe déjà.</small>}</label>
          </div>
          <label className="field-label mt-6">{copy.relatedOrders}<span className="field-help">Plusieurs commandes peuvent être associées au même document.</span>
            <input className="text-input mb-3" placeholder="Filtrer par référence ou fournisseur" value={orderSearch} onChange={(event) => setOrderSearch(event.target.value)} />
            <div className="order-select-list">{availableOrders.map((order) => <label className="order-select-option" key={order.id}><input type="checkbox" checked={selectedOrders.includes(order.id)} onChange={(event) => setSelectedOrders((current) => event.target.checked ? [...current, order.id] : current.filter((item) => item !== order.id))} /><span><strong>{order.reference}</strong><small>{order.fournisseur} · {order.date}</small></span><StatusBadge status={order.statutReception} /></label>)}</div>
          </label>
        </section>
        <section className="panel form-panel">
          <div className="form-section-heading"><span className="step-number">02</span><div><h2>Capture ou import</h2><p>Ajoutez des images ou un seul PDF. Les images sont réduites à 2 000 px et regroupées en PDF avant envoi.</p></div></div>
          <input ref={inputRef} className="sr-only" type="file" accept="image/jpeg,image/png,image/webp,application/pdf" capture="environment" multiple onChange={(event) => addFiles(event.target.files)} />
          <div className="dropzone" onClick={() => inputRef.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); addFiles(event.dataTransfer.files) }} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click() }}>
            <span className="upload-icon">↑</span><strong>Déposez vos fichiers ici</strong><span>ou cliquez pour importer · JPEG, PNG ou PDF · 20 Mo maximum par page</span>
            <span className="button button-secondary mt-3">{copy.uploadFile}</span>
          </div>
          {files.length > 0 && <div className="page-files"><div className="files-heading"><strong>{files.length} page(s) sélectionnée(s)</strong><span>Réorganisez ou retirez les pages avant l’envoi.</span></div>{files.map((file, index) => <div className="file-row" key={`${file.name}-${index}`}><span className="file-thumbnail">{file.type === 'application/pdf' ? 'PDF' : 'IMG'}</span><span className="file-name">{file.name}</span>{file.type.startsWith('image/') && <button type="button" className="button button-quiet" onClick={() => { setCropMargin(5); setCropIndex(index) }}>Recadrer</button>}<button type="button" className="icon-button" aria-label="Déplacer la page vers le haut" disabled={index === 0} onClick={() => setFiles((current) => { const next = [...current]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next })}>↑</button><button type="button" className="icon-button" aria-label="Déplacer la page vers le bas" disabled={index === files.length - 1} onClick={() => setFiles((current) => { const next = [...current]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; return next })}>↓</button><button type="button" className="icon-button icon-danger" aria-label={`Retirer ${file.name}`} onClick={() => setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))}>×</button></div>)}</div>}
        </section>
        {errorMessage && <p className="form-error-banner" role="alert">{errorMessage} Vous pouvez réessayer sans resélectionner vos pages.</p>}
        <div className="form-actions"><Link className="button button-secondary" to="/bc">{copy.cancel}</Link><button className="button button-primary" disabled={upload.isPending || duplicateNumber}>{upload.isPending ? 'Envoi en cours…' : upload.isError ? 'Réessayer l’envoi' : copy.sendDocument} <span>→</span></button></div>
      </form>
      <ConfirmDialog open={cropIndex !== null} title="Recadrer cette page" description="Ajustez la marge à retirer uniformément autour de l’image." confirmLabel="Appliquer le recadrage" onCancel={() => setCropIndex(null)} onConfirm={() => void applyCrop()}>
        {cropFile && cropPreview && <img className="crop-preview" src={cropPreview} alt="Aperçu de la page à recadrer" />}
        <label className="field-label mt-4">Marge retirée : {cropMargin}%<input type="range" min="0" max="25" step="1" value={cropMargin} onChange={(event) => setCropMargin(Number(event.target.value))} /></label>
      </ConfirmDialog>
    </div>
  )
}

export function ReceiptPage() {
  const { id } = useParams()
  const { me } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['order', id], queryFn: () => request<PurchaseOrder>(`/api/bc/${id}`) })
  const scansQuery = useQuery({ queryKey: ['scans'], queryFn: () => request<ScannedDocument[]>('/api/scans') })
  const linkedDeliveryNotes = scansQuery.data?.filter((scan) => scan.type === 'BL' && scan.bc.includes(query.data?.reference ?? '')) ?? []
  const [quantities, setQuantities] = useState<number[]>([])
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [deliveryNumber, setDeliveryNumber] = useState('')
  const [remarks, setRemarks] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [success, setSuccess] = useState(false)
  const [busy, setBusy] = useState(false)
  const lines = query.data?.lignes ?? []
  const mutation = useMutation({
    mutationFn: (payload: { draftId?: number; lines: Receipt['lignes']; password?: string }) => {
      const values = { lignes: payload.lines, numeroBl: deliveryNumber, remarques: remarks }
      const draft = payload.draftId
        ? request<Receipt>(`/api/br/${payload.draftId}`, jsonRequest('PATCH', values))
        : request<Receipt>(`/api/bc/${id}/br`, jsonRequest('POST', values))
      return draft.then((saved) => request<Receipt>(`/api/br/${saved.id}/valider`, jsonRequest('POST', { mot_de_passe: payload.password })))
    },
    onSuccess: (result) => {
      setReceipt(result)
      setSuccess(true)
      setConfirmOpen(false)
      setErrorMessage('')
      void queryClient.invalidateQueries({ queryKey: ['order', id] })
    },
    onError: (error: Error) => setErrorMessage(error.message),
  })
  const saveDraft = useMutation({
    mutationFn: () => receipt
      ? request<Receipt>(`/api/br/${receipt.id}`, jsonRequest('PATCH', { lignes: receiptLines, numeroBl: deliveryNumber, remarques: remarks }))
      : request<Receipt>(`/api/bc/${id}/br`, jsonRequest('POST', { lignes: receiptLines, numeroBl: deliveryNumber, remarques: remarks })),
    onSuccess: (saved) => { setReceipt(saved); setErrorMessage(copy.draftSaved) },
    onError: (error: Error) => setErrorMessage(error.message),
  })
  const receiptLines = lines.map((line, index) => ({ ligneId: line.id, article: line.article, quantite: quantities[index] ?? 0 }))
  const invalidQuantity = lines.some((line, index) => (quantities[index] ?? 0) < 0 || (quantities[index] ?? 0) > line.commande - line.recue)

  if (!useCan('generer_br') || me?.entreprise.erp_type !== 'urium') return <Navigate to="/" replace />
  if (query.isPending) return <LoadingState />
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  if (!query.data) return <EmptyState title="Bon de commande introuvable" />
  if (success && receipt) return (
    <section className="success-card">
      <span className="success-check">✓</span><p className="eyebrow">RÉCEPTION ENREGISTRÉE</p><h1>{copy.receiptConfirmed}</h1>
      <p className="success-reference">{receipt.reference}</p><p>Réception validée électroniquement · document prêt à être téléchargé.</p>
      <div className="pdf-preview"><div className="pdf-sheet"><span>BR</span><strong>{receipt.reference}</strong><small>{query.data.reference} · {query.data.fournisseur}</small><i>Validation électronique</i></div></div>
      <div className="success-actions"><button className="button button-secondary" onClick={() => window.print()}>Imprimer</button><button className="button button-secondary" onClick={() => void downloadFile(`/api/br/${receipt.id}/pdf`, `${receipt.reference}.pdf`).catch((error: Error) => setErrorMessage(error.message))}>↓ Télécharger le PDF</button><button className="button button-primary" onClick={() => navigate(`/bc/${id}`)}>Retour au BC</button></div>
      {errorMessage && <p className="inline-notice">{errorMessage}</p>}
    </section>
  )

  return (
    <div className="page-stack">
      <Link to={`/bc/${id}`} className="back-link">← Retour au dossier {query.data.reference}</Link>
      <PageTitle eyebrow="RÉCEPTION · ÉTAPE 1 SUR 2" title={copy.createReceipt} description={`${query.data.reference} · ${query.data.fournisseur}`} />
      <div className="receipt-progress"><span className="receipt-progress-active">1 <small>Quantités reçues</small></span><i /><span>2 <small>Confirmation</small></span></div>
      <section className="panel receipt-panel">
        <div className="panel-heading"><div><p className="eyebrow">ARTICLES COMMANDÉS</p><h2>Indiquez les quantités réceptionnées</h2></div><button className="button button-secondary" onClick={() => setQuantities(lines.map((line) => line.commande - line.recue))}>{copy.receiveAll}</button></div>
        <div className="receipt-lines">{lines.map((line, index) => {
          const remaining = line.commande - line.recue
          const current = quantities[index] ?? 0
          return <div className="receipt-line" key={line.article}><div className="receipt-item"><strong>{line.article}</strong><span>Commandé : {line.commande} {line.unite} <i>·</i> Déjà reçu : {line.recue} {line.unite} <i>·</i> Reste : <b>{remaining} {line.unite}</b></span></div><div className="quantity-control"><button type="button" aria-label={`Diminuer ${line.article}`} onClick={() => setQuantities((currentValues) => currentValues.map((value, itemIndex) => itemIndex === index ? Math.max(0, value - 1) : value))}>−</button><input aria-label={`${copy.receiveNow} ${line.article}`} type="number" min="0" max={remaining} value={current} onChange={(event) => setQuantities((values) => lines.map((_, itemIndex) => itemIndex === index ? Number(event.target.value) : values[itemIndex] ?? 0))} /><button type="button" aria-label={`Augmenter ${line.article}`} disabled={current >= remaining} onClick={() => setQuantities((currentValues) => currentValues.map((value, itemIndex) => itemIndex === index ? Math.min(remaining, value + 1) : value))}>＋</button></div></div>
        })}</div>
        <div className="form-fields-grid mt-5"><label className="field-label">Numéro du BL fournisseur (facultatif)<input className="text-input" list="linked-delivery-notes" value={deliveryNumber} onChange={(event) => setDeliveryNumber(event.target.value)} placeholder="Saisir ou choisir un BL scanné" /><datalist id="linked-delivery-notes">{linkedDeliveryNotes.map((scan) => <option key={scan.id} value={scan.numero}>{scan.fournisseur}</option>)}</datalist></label><label className="field-label">Remarques (facultatif)<input className="text-input" value={remarks} onChange={(event) => setRemarks(event.target.value)} placeholder="Ajouter une remarque à la réception" /></label></div>
        {invalidQuantity && <p className="field-error mt-4">La quantité reçue ne peut pas dépasser le reste à recevoir.</p>}
        {errorMessage && <p className="form-error-banner mt-4" role="alert">{errorMessage}</p>}
        <div className="form-actions"><button type="button" className="button button-secondary" disabled={saveDraft.isPending} onClick={() => saveDraft.mutate()}>{saveDraft.isPending ? 'Enregistrement…' : copy.saveDraft}</button><button type="button" className="button button-primary" disabled={invalidQuantity || !quantities.some((quantity) => quantity > 0)} onClick={() => setConfirmOpen(true)}>{copy.validateReceipt} →</button></div>
      </section>
      <ConfirmDialog open={confirmOpen} title="Confirmer la réception ?" description="Vous confirmez avoir réceptionné les quantités indiquées. Cette action est définitive." confirmLabel={copy.validateReceipt} busy={busy} onCancel={() => setConfirmOpen(false)} onConfirm={() => {
        if (busy) return
        if (me.options.reauth_validation_br && !password) { setErrorMessage('Saisissez votre mot de passe pour confirmer.'); return }
        setBusy(true)
        mutation.mutate({ draftId: receipt?.id, lines: receiptLines, password }, { onSettled: () => setBusy(false) })
      }}>
        {me.options.reauth_validation_br && <label className="field-label mt-4">{copy.password}<input type="password" autoComplete="current-password" className="text-input" value={password} onChange={(event) => setPassword(event.target.value)} /></label>}
      </ConfirmDialog>
    </div>
  )
}

function JournalPage() {
  const [period, setPeriod] = useState('30')
  const query = useQuery({ queryKey: ['journal', period], queryFn: () => request<ActivityEntry[]>(`/api/journal?periode=${period}`) })
  const [search, setSearch] = useState('')
  const rows = useMemo(() => query.data?.filter((row) => `${row.action} ${row.utilisateur} ${row.detail ?? ''} ${row.bonCommande ?? ''}`.toLocaleLowerCase('fr').includes(search.toLocaleLowerCase('fr'))) ?? [], [query.data, search])
  return <div className="page-stack"><PageTitle eyebrow="TRAÇABILITÉ" title={copy.journal} description="Historique en lecture seule des actions effectuées dans l’application." /><section className="filter-bar"><label className="search-control"><span>⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filtrer par utilisateur ou action" /></label><label className="field-label">Période<select className="text-input" aria-label="Période du journal" value={period} onChange={(event) => setPeriod(event.target.value)}><option value="7">7 derniers jours</option><option value="30">30 derniers jours</option><option value="90">90 derniers jours</option><option value="365">12 derniers mois</option></select></label></section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">{rows.length} ÉVÉNEMENTS</p><h2>Activité récente</h2></div><span className="read-only-tag">Lecture seule</span></div>{query.isPending ? <LoadingState /> : query.error ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : <ActivityRows rows={rows} />}</section></div>
}

function UsersPage() {
  const [newUser, setNewUser] = useState(false)
  const [message, setMessage] = useState('')
  const queryClient = useQueryClient()
  const users = useQuery({ queryKey: ['users'], queryFn: () => request<{ utilisateurs: Array<{ id: string | number; nom: string; identifiant: string; role: string; entreprise: string; actif: boolean }>; rolesDisponibles: string[] }>('/api/utilisateurs') })
  const userRows = users.data?.utilisateurs ?? []
  const allowedRoles = users.data?.rolesDisponibles ?? []
  const [userName, setUserName] = useState('')
  const [userIdentifier, setUserIdentifier] = useState('')
  const [userRole, setUserRole] = useState('')
  const addUser = useMutation({
    mutationFn: () => request<{ identifiant: string; mot_de_passe_temporaire: string }>('/api/utilisateurs', jsonRequest('POST', { nom: userName, identifiant: userIdentifier, role: userRole })),
    onSuccess: (credentials) => { setMessage(`Utilisateur ajouté. Identifiant : ${credentials.identifiant} · Mot de passe temporaire : ${credentials.mot_de_passe_temporaire} (à communiquer une seule fois).`); setNewUser(false); setUserName(''); setUserIdentifier(''); setUserRole(''); void queryClient.invalidateQueries({ queryKey: ['users'] }) },
    onError: (error: Error) => setMessage(error.message),
  })
  const updateUser = useMutation({
    mutationFn: ({ id, changes }: { id: string | number; changes: { role?: string; actif?: boolean; reset_password?: boolean } }) =>
      request<{ identifiant: string; mot_de_passe_temporaire?: string }>(`/api/utilisateurs/${id}`, jsonRequest('PATCH', changes)),
    onSuccess: (result) => { setMessage(result.mot_de_passe_temporaire ? `Nouveau mot de passe temporaire pour ${result.identifiant} : ${result.mot_de_passe_temporaire} (à communiquer une seule fois).` : 'Informations utilisateur mises à jour.'); void queryClient.invalidateQueries({ queryKey: ['users'] }); void queryClient.invalidateQueries({ queryKey: ['me'] }) },
    onError: (error: Error) => setMessage(error.message),
  })
  return (
    <div className="page-stack">
      <PageTitle eyebrow="ESPACE ADMINISTRATEUR" title="Utilisateurs" description="Gérez les accès à l’espace de travail." action={<button className="button button-primary" onClick={() => setNewUser((open) => !open)}>＋ Ajouter un utilisateur</button>} />
      {message && <p className="inline-notice" role="status">{message}</p>}
      {newUser && <form className="panel user-create-form" onSubmit={(event) => { event.preventDefault(); addUser.mutate() }}><label className="field-label">Nom complet<input className="text-input" required value={userName} onChange={(event) => setUserName(event.target.value)} /></label><label className="field-label">Identifiant de connexion<input className="text-input" autoComplete="off" required value={userIdentifier} onChange={(event) => setUserIdentifier(event.target.value)} /></label><label className="field-label">Rôle<select className="text-input" required value={userRole} onChange={(event) => setUserRole(event.target.value)}><option value="">Choisir un rôle</option>{allowedRoles.map((role) => <option key={role}>{role}</option>)}</select></label><button className="button button-primary" disabled={addUser.isPending}>Créer l’accès</button></form>}
      <section className="panel table-panel"><div className="panel-heading"><div><p className="eyebrow">{userRows.length} COMPTES</p><h2>Comptes utilisateurs</h2></div></div>{users.isPending ? <LoadingState /> : users.error ? <ErrorState error={users.error} retry={() => void users.refetch()} /> : <div className="table-scroll"><table className="data-table card-table"><thead><tr><th>Utilisateur</th><th>Entreprise</th><th>Rôle</th><th>Statut</th><th>Actions</th></tr></thead><tbody>{userRows.map((user) => <tr key={user.id}><td data-label="Utilisateur" className="table-reference">{user.nom}<small className="block font-normal">Identifiant : {user.identifiant}</small></td><td data-label="Entreprise">{user.entreprise}</td><td data-label="Rôle"><label className="sr-only" htmlFor={`role-${user.id}`}>Rôle de {user.nom}</label><select id={`role-${user.id}`} className="table-select" value={user.role} onChange={(event) => { const role = event.target.value; if (window.confirm(`Changer le rôle de ${user.nom} pour ${role} ?`)) updateUser.mutate({ id: user.id, changes: { role } }); else event.target.value = user.role }}>{allowedRoles.map((role) => <option key={role}>{role}</option>)}</select></td><td data-label="Statut"><StatusBadge status={user.actif ? 'synchronise' : 'annule'} /></td><td data-label="Actions"><button className="button button-quiet" onClick={() => { if (!user.actif || window.confirm(`Désactiver le compte de ${user.nom} ?`)) updateUser.mutate({ id: user.id, changes: { actif: !user.actif } }) }}>{user.actif ? 'Désactiver' : 'Réactiver'}</button><button className="button button-quiet" onClick={() => updateUser.mutate({ id: user.id, changes: { reset_password: true } })}>Réinitialiser</button></td></tr>)}</tbody></table></div>}</section>
    </div>
  )
}

function ConnectionsPage() {
  const { me } = useAuth()
  const query = useQuery({
    queryKey: ['service-status'],
    queryFn: () => request<{ erp: { statut: string; detail: string; verifieLe: string }; drive: { statut: string; detail: string; verifieLe: string } }>('/api/etat-services'),
  })
  if (query.isPending) return <LoadingState />
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  const services = [
    { name: copy.drive, description: 'Stockage et synchronisation documentaire', status: query.data.drive },
    { name: copy.erp, description: `${me?.entreprise.erp_type.toUpperCase()} · Commandes et réceptions`, status: query.data.erp },
  ]
  return <div className="page-stack"><PageTitle eyebrow="ADMINISTRATION" title={copy.connectionsTitle} description="Vérification en direct des services associés à votre espace." action={<button className="button button-secondary" disabled={query.isFetching} onClick={() => void query.refetch()}>{query.isFetching ? 'Vérification…' : '↻ Vérifier à nouveau'}</button>} /><section className="connection-grid">{services.map((service) => <article className="panel connection-card" key={service.name}><span className="connection-icon">⌁</span><div><h2>{service.name}</h2><p>{service.description}</p><small>{service.status.detail}</small></div><StatusBadge status={service.status.statut} /><span className="connection-last">Vérifié le {new Date(service.status.verifieLe).toLocaleString('fr-FR')}</span></article>)}</section></div>
}

function ProfilePage() {
  const { me } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [message, setMessage] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const changePassword = useMutation({
    mutationFn: () => request<{ detail: string }>('/api/auth/changer-mot-de-passe/', jsonRequest('POST', {
      ancien_mot_de_passe: currentPassword,
      nouveau_mot_de_passe: newPassword,
      confirmation: passwordConfirmation,
    })),
    onSuccess: async (result) => {
      setMessage(result.detail)
      setCurrentPassword('')
      setNewPassword('')
      setPasswordConfirmation('')
      await queryClient.invalidateQueries({ queryKey: ['me'] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  const logout = useMutation({
    mutationFn: () => request<{ detail: string }>('/api/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ['me'] })
      navigate('/connexion')
    },
    onError: (error: Error) => setMessage(error.message),
  })
  return <div className="page-stack"><PageTitle eyebrow="ESPACE PERSONNEL" title={copy.profile} description="Informations de votre compte et préférences de sécurité." /><section className="panel profile-card"><div className="profile-identity"><span className="profile-avatar profile-avatar-large">{me?.utilisateur.nom.split(' ').map((part) => part[0]).slice(0, 2).join('')}</span><div><h2>{me?.utilisateur.nom}</h2><p>{me?.utilisateur.role} · {me?.entreprise.nom}</p></div></div><div className="profile-detail"><span>Entreprise</span><strong>{me?.entreprise.nom}</strong></div><div className="profile-detail"><span>Rôle</span><strong>{me?.utilisateur.role}</strong></div>{me?.options.mot_de_passe_a_changer && <p className="form-error-banner" role="alert">Ce mot de passe temporaire doit être remplacé avant de poursuivre.</p>}<form className="password-form" onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); changePassword.mutate() }}><h3>Changer le mot de passe</h3><label className="field-label">Mot de passe actuel<input className="text-input" type="password" autoComplete="current-password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label><label className="field-label">Nouveau mot de passe<input className="text-input" type="password" autoComplete="new-password" required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></label><label className="field-label">Confirmer le nouveau mot de passe<input className="text-input" type="password" autoComplete="new-password" required value={passwordConfirmation} onChange={(event) => setPasswordConfirmation(event.target.value)} /></label><button className="button button-secondary" disabled={changePassword.isPending}>{changePassword.isPending ? 'Mise à jour…' : 'Mettre à jour le mot de passe'}</button></form>{message && <p className="inline-notice">{message}</p>}<button className="button button-danger mt-5" disabled={logout.isPending} onClick={() => logout.mutate()}>↪ Se déconnecter</button></section></div>
}

function LoginPage() {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const queryClient = useQueryClient()
  const { me } = useAuth()
  const login = useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      request<MeResponse>('/api/auth/login', jsonRequest('POST', credentials)),
    onSuccess: async (user) => {
      await queryClient.cancelQueries({ queryKey: ['me'] })
      queryClient.setQueryData(['me'], user)
      navigate('/')
    },
    onError: (reason: Error) => setError(reason.message),
  })
  return <div className="login-screen"><form className="login-card" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); const username = String(data.get('identifiant') ?? '').trim(); const password = String(data.get('mot_de_passe') ?? ''); if (!username || !password) { setError('Saisissez votre identifiant et votre mot de passe.'); return } setError(''); login.mutate({ username, password }) }}><span className="brand-symbol">{me?.entreprise.logo ?? 'AC'}</span><p className="eyebrow">{me?.entreprise.nom ?? 'GESTION DES ACHATS'}</p><h1>Bienvenue</h1><p>Connectez-vous pour accéder à vos dossiers d’achat.</p><label className="field-label">Identifiant<input className="text-input" name="identifiant" autoComplete="username" /></label><label className="field-label">Mot de passe<input className="text-input" name="mot_de_passe" type="password" autoComplete="current-password" /></label>{error && <p className="field-error" role="alert">{error}</p>}<button className="button button-primary w-full" disabled={login.isPending}>{login.isPending ? 'Connexion…' : 'Se connecter'} <span>→</span></button></form></div>
}

function NotFoundPage() {
  return <section className="state-card"><div className="state-icon">?</div><div><h2>{copy.notFound}</h2><Link className="text-link" to="/">Retour à l’accueil →</Link></div></section>
}

export default function App() {
  const { loading, error, me } = useAuth()
  const location = useLocation()
  const canReadOwn = useCan('voir_siens')
  const canReadAll = useCan('voir_tous')
  const canReadDocuments = canReadOwn || canReadAll
  const canScan = useCan('scanner')
  const canReceive = useCan('generer_br')

  if (loading && location.pathname !== '/connexion') return <LoadingState />
  if (location.pathname !== '/connexion' && (error || !me)) return <Navigate to="/connexion" replace />
  if (me?.options.mot_de_passe_a_changer && location.pathname !== '/profil') return <Navigate to="/profil" replace />

  return (
    <Routes>
      <Route path="/connexion" element={<LoginPage />} />
      <Route path="*" element={<AppShell><Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/bc" element={canReadDocuments || canReceive || canScan ? <OrdersPage /> : <Navigate to="/" replace />} />
        <Route path="/bc/:id" element={canReadDocuments || canReceive || canScan ? <OrderDetailPage /> : <Navigate to="/" replace />} />
        <Route path="/bc/:id/br" element={<ProtectedRoute permission="generer_br"><ReceiptPage /></ProtectedRoute>} />
        <Route path="/documents" element={<ProtectedRoute permission={canReadDocuments ? 'voir_tous' : 'voir_siens'}><DocumentsPage /></ProtectedRoute>} />
        <Route path="/documents/nouveau" element={<ProtectedRoute permission="scanner"><ScanFormPage /></ProtectedRoute>} />
        <Route path="/documents/:id" element={<DocumentDetailRoute />} />
        <Route path="/journal" element={<ProtectedRoute permission="voir_audit"><JournalPage /></ProtectedRoute>} />
        <Route path="/utilisateurs" element={<ProtectedRoute permission="gerer_utilisateurs"><UsersPage /></ProtectedRoute>} />
        <Route path="/connexions" element={<ProtectedRoute permission="gerer_utilisateurs"><ConnectionsPage /></ProtectedRoute>} />
        <Route path="/profil" element={<ProfilePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes></AppShell>} />
    </Routes>
  )
}

function DocumentDetailRoute() {
  const { id } = useParams()
  const canSeeOwn = useCan('voir_siens')
  const canSeeAll = useCan('voir_tous')
  const canSee = canSeeOwn || canSeeAll
  const canDelete = useCan('supprimer')
  const canReplace = useCan('remplacer')
  const canResync = useCan('resynchroniser')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const replaceInput = useRef<HTMLInputElement>(null)
  const [message, setMessage] = useState('')
  const query = useQuery({ queryKey: ['scan', id], queryFn: () => request<ScannedDocument>(`/api/scans/${id}`) })
  const action = useMutation({
    mutationFn: ({ method, file }: { method: 'DELETE' | 'PATCH' | 'POST'; file?: File }): Promise<ScannedDocument & { avertissement?: string }> => {
      if (method === 'PATCH' && file) {
        const formData = new FormData()
        formData.set('fichier', file)
        return request<ScannedDocument & { avertissement?: string }>(`/api/scans/${id}`, { method, body: formData })
      }
      return request<ScannedDocument & { avertissement?: string }>(`/api/scans/${id}${method === 'POST' ? '/resynchroniser' : ''}`, { method })
    },
    onSuccess: (data, method) => {
      if (data.avertissement) setMessage(data.avertissement)
      void queryClient.invalidateQueries({ queryKey: ['scans'] })
      if (method.method === 'DELETE') navigate('/documents')
      else void queryClient.invalidateQueries({ queryKey: ['scan', id] })
    },
    onError: (error: Error) => setMessage(error.message),
  })
  if (!canSee) return <Navigate to="/" replace />
  if (query.isPending) return <LoadingState />
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />
  if (!query.data) return <EmptyState title="Document introuvable" />
  const scan = query.data
  return <div className="page-stack"><Link className="back-link" to="/documents">← Retour aux documents</Link><PageTitle eyebrow={`DOCUMENT · ${scan.type}`} title={scan.numero} description={`${scan.fournisseur} · ajouté le ${new Date(scan.date).toLocaleString('fr-FR')}`} action={<StatusBadge status={scan.statut} />} /><section className="document-detail-grid"><div className="panel document-preview"><div className="preview-toolbar"><strong>Document source</strong><span>Conservé sur Google Drive</span></div><div className="empty-state"><span className="empty-state-mark">▧</span><h3>Fichier numérisé</h3><p>Le document original est stocké dans l’espace Drive de l’entreprise.</p>{scan.driveLink && <a className="button button-primary mt-4" href={scan.driveLink} target="_blank" rel="noreferrer">Ouvrir le document dans Drive ↗</a>}</div></div><aside className="panel document-metadata"><h2>Détails du document</h2><div className="profile-detail"><span>Type</span><strong>{scan.type === 'BL' ? 'Bon de livraison' : 'Facture fournisseur'}</strong></div><div className="profile-detail"><span>Numéro</span><strong>{scan.numero}</strong></div><div className="profile-detail"><span>Ajouté par</span><strong>{scan.auteur}</strong></div><div className="profile-detail"><span>Synchronisation</span><StatusBadge status={scan.statut} /></div>{scan.messageErreur && <p className="form-error-banner">{scan.messageErreur}</p>}{message && <p className="inline-notice" role="status">{message}</p>}<h3 className="mt-5">Bons de commande associés</h3>{scan.bc.map((bc, index) => <Link to={`/bc/${scan.bcIds?.[index] ?? bc.slice(-4)}`} className="associated-order" key={bc}>{bc} <span>↗</span></Link>)}<input ref={replaceInput} className="sr-only" type="file" accept="image/jpeg,image/png,application/pdf" onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; if (file.size > 20 * 1024 * 1024) { setMessage('Fichier trop lourd. La taille maximale est de 20 Mo.'); return } if (!['application/pdf', 'image/jpeg', 'image/png'].includes(file.type)) { setMessage('Format refusé. Choisissez un fichier JPEG, PNG ou PDF.'); return } action.mutate({ method: 'PATCH', file }) }} /> <div className="document-actions">{canResync && scan.statut === 'echec' && <button className="button button-secondary" onClick={() => action.mutate({ method: 'POST' })}>↻ Resynchroniser</button>}{canReplace && <button className="button button-secondary" onClick={() => replaceInput.current?.click()}>Remplacer le fichier</button>}{canDelete && <button className="button button-danger" onClick={() => window.confirm(`Supprimer le document ${scan.numero} ?`) && action.mutate({ method: 'DELETE' })}>Supprimer le document</button>}</div></aside></section></div>
}
