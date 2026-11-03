export type Permission =
  | 'scanner'
  | 'voir_siens'
  | 'voir_tous'
  | 'remplacer'
  | 'supprimer'
  | 'resynchroniser'
  | 'voir_audit'
  | 'gerer_utilisateurs'
  | 'generer_br'
  | 'annuler_br'

export type DocumentType = 'BL' | 'FACTURE'
export type CompanyCode = 'odoo_co' | 'urium_co'
export type ErpType = 'odoo' | 'urium'

export interface MeResponse {
  utilisateur: { nom: string; role: string }
  entreprise: {
    code: CompanyCode
    nom: string
    logo: string
    couleur: string
    erp_type: ErpType
  }
  permissions: Permission[]
  types_scannables: DocumentType[]
  options: { reauth_validation_br: boolean; mot_de_passe_a_changer?: boolean }
}

export interface PurchaseOrder {
  id: number
  reference: string
  fournisseur: string
  date: string
  statutErp: string
  montant: number
  devise: string
  statutReception: 'non_recu' | 'partiellement_recu' | 'entierement_recu'
  completude: number
  lignes: Array<{
    id?: number
    article: string
    commande: number
    recue: number
    unite: string
  }>
  br: number
  bl: number
  factures: number
}

export interface ScannedDocument {
  id: number
  type: DocumentType
  numero: string
  fournisseur: string
  bc: string[]
  bcIds?: number[]
  statut: 'synchronise' | 'en_attente' | 'echec' | 'non_applicable'
  auteur: string
  date: string
  messageErreur?: string
  driveLink?: string
  avertissement?: string
}

export interface Receipt {
  id: number
  reference: string
  bcId: number
  statut: 'brouillon' | 'valide' | 'annule'
  lignes: Array<{ ligneId?: number; article: string; quantite: number }>
  numeroBl?: string
  remarques?: string
}
