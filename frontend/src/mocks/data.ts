import type { MeResponse, Permission, PurchaseOrder, ScannedDocument } from '../types'

export interface DemoPersona {
  id: string
  label: string
  me: MeResponse
}

const odooCompany = {
  code: 'odoo_co' as const,
  nom: 'Odoo Construction',
  logo: 'OC',
  couleur: '#0e7490',
  erp_type: 'odoo' as const,
}

const uriumCompany = {
  code: 'urium_co' as const,
  nom: 'Urium Industries',
  logo: 'UI',
  couleur: '#6d4aff',
  erp_type: 'urium' as const,
}

const permissions = {
  operator: ['scanner', 'voir_siens'],
  accountant: ['scanner', 'voir_tous', 'resynchroniser', 'generer_br'],
  manager: ['scanner', 'voir_tous', 'resynchroniser', 'remplacer', 'supprimer', 'voir_audit', 'generer_br'],
  reader: ['voir_tous', 'voir_audit'],
  admin: ['scanner', 'voir_tous', 'resynchroniser', 'remplacer', 'supprimer', 'voir_audit', 'gerer_utilisateurs', 'generer_br', 'annuler_br'],
  storekeeper: ['scanner', 'voir_siens', 'generer_br'],
  purchasing: ['scanner', 'voir_tous', 'generer_br'],
  director: ['scanner', 'voir_tous', 'resynchroniser', 'remplacer', 'supprimer', 'voir_audit', 'generer_br', 'annuler_br'],
} satisfies Record<string, Permission[]>

const persona = (
  id: string,
  label: string,
  company: typeof odooCompany | typeof uriumCompany,
  role: string,
  access: Permission[],
  types: MeResponse['types_scannables'],
): DemoPersona => ({
  id,
  label,
  me: {
    utilisateur: { nom: role === 'admin' ? 'Camille Martin' : 'Sophie Laurent', role },
    entreprise: company,
    permissions: access,
    types_scannables: types,
    options: { reauth_validation_br: id === 'urium-admin', mot_de_passe_a_changer: false },
  },
})

export const personas: DemoPersona[] = [
  persona('odoo-operator', 'Odoo · Opérateur', odooCompany, 'operateur', permissions.operator, ['BL']),
  persona('odoo-accountant', 'Odoo · Comptable', odooCompany, 'comptable', permissions.accountant.filter((p) => p !== 'generer_br'), ['BL', 'FACTURE']),
  persona('odoo-manager', 'Odoo · Responsable', odooCompany, 'responsable', permissions.manager.filter((p) => p !== 'generer_br'), ['BL', 'FACTURE']),
  persona('odoo-reader', 'Odoo · Lecteur', odooCompany, 'lecteur', permissions.reader, []),
  persona('odoo-admin', 'Odoo · Admin', odooCompany, 'admin', permissions.admin.filter((p) => p !== 'generer_br' && p !== 'annuler_br'), ['BL', 'FACTURE']),
  persona('urium-storekeeper', 'Urium · Magasinier', uriumCompany, 'magasinier', permissions.storekeeper, ['BL']),
  persona('urium-purchasing', 'Urium · Achats', uriumCompany, 'achats', permissions.purchasing, ['BL', 'FACTURE']),
  persona('urium-director', 'Urium · Directeur', uriumCompany, 'directeur', permissions.director, ['BL', 'FACTURE']),
  persona('urium-admin', 'Urium · Admin', uriumCompany, 'admin', permissions.admin, ['BL', 'FACTURE']),
]

export const purchaseOrders: PurchaseOrder[] = [
  {
    id: 148,
    reference: 'BC-2026-0148',
    fournisseur: 'Alpha Logistics',
    date: '2026-10-28',
    statutErp: 'confirme',
    montant: 158420,
    devise: 'MAD',
    statutReception: 'partiellement_recu',
    completude: 68,
    lignes: [
      { article: 'Câble électrique 3G2.5', commande: 120, recue: 80, unite: 'bobines' },
      { article: 'Disjoncteur différentiel 40A', commande: 24, recue: 12, unite: 'pièces' },
      { article: 'Gaine ICTA Ø20', commande: 200, recue: 0, unite: 'mètres' },
    ],
    br: 2,
    bl: 3,
    factures: 1,
  },
  {
    id: 149,
    reference: 'BC-2026-0149',
    fournisseur: 'Benoit Industriel',
    date: '2026-10-27',
    statutErp: 'confirme',
    montant: 87450,
    devise: 'MAD',
    statutReception: 'non_recu',
    completude: 25,
    lignes: [
      { article: 'Pompe de relevage inox', commande: 4, recue: 0, unite: 'pièces' },
      { article: 'Kit raccordement DN50', commande: 4, recue: 0, unite: 'kits' },
    ],
    br: 0,
    bl: 1,
    factures: 0,
  },
  {
    id: 150,
    reference: 'BC-2026-0150',
    fournisseur: 'Nexus Matériel',
    date: '2026-10-25',
    statutErp: 'confirme',
    montant: 220000,
    devise: 'MAD',
    statutReception: 'entierement_recu',
    completude: 100,
    lignes: [{ article: 'Groupe électrogène 80 kVA', commande: 2, recue: 2, unite: 'unités' }],
    br: 4,
    bl: 4,
    factures: 2,
  },
  {
    id: 152,
    reference: 'BC-2026-0152',
    fournisseur: 'Centrale Services',
    date: '2026-10-23',
    statutErp: 'confirme',
    montant: 64120,
    devise: 'MAD',
    statutReception: 'partiellement_recu',
    completude: 58,
    lignes: [{ article: 'Équipement de protection individuelle', commande: 60, recue: 36, unite: 'lots' }],
    br: 1,
    bl: 2,
    factures: 0,
  },
]

export const scannedDocuments: ScannedDocument[] = [
  { id: 41, type: 'BL', numero: 'BL-AL-8091', fournisseur: 'Alpha Logistics', bc: ['BC-2026-0148'], statut: 'synchronise', auteur: 'Sophie Laurent', date: '2026-10-30T09:18:00' },
  { id: 42, type: 'FACTURE', numero: 'FAC-2026-332', fournisseur: 'Nexus Matériel', bc: ['BC-2026-0150'], statut: 'echec', auteur: 'Karim Benali', date: '2026-10-30T08:42:00', messageErreur: 'Le dossier Drive est temporairement indisponible.' },
  { id: 43, type: 'BL', numero: 'BL-BI-1072', fournisseur: 'Benoit Industriel', bc: ['BC-2026-0149', 'BC-2026-0152'], statut: 'en_attente', auteur: 'Camille Martin', date: '2026-10-29T16:25:00' },
  { id: 44, type: 'FACTURE', numero: 'FAC-CS-886', fournisseur: 'Centrale Services', bc: ['BC-2026-0152'], statut: 'synchronise', auteur: 'Sophie Laurent', date: '2026-10-29T14:10:00' },
]

export const activity = [
  { id: 1, action: 'Document BL-AL-8091 ajouté', utilisateur: 'Sophie Laurent', date: '30 oct. 2026 · 09:18' },
  { id: 2, action: 'Réception partielle enregistrée sur BC-2026-0148', utilisateur: 'Karim Benali', date: '30 oct. 2026 · 08:55' },
  { id: 3, action: 'Facture FAC-2026-332 — échec de synchronisation', utilisateur: 'Karim Benali', date: '30 oct. 2026 · 08:42' },
  { id: 4, action: 'Brouillon BR-2026-0038 créé', utilisateur: 'Camille Martin', date: '29 oct. 2026 · 16:02' },
]
