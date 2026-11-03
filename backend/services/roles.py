# Toutes les permissions possibles
ALL_PERMISSIONS = frozenset([
    "scanner", "voir_siens", "voir_tous", "remplacer", "supprimer",
    "resynchroniser", "voir_audit", "gerer_utilisateurs",
    "generer_br", "annuler_br",
])

# Types de documents scannables
TYPES_SCANNABLES = ["BL", "FACTURE"]

# Définition des rôles par ERP_TYPE
ROLES = {
    "odoo": {
        "operateur": {
            "label": "Opérateur (magasinier / réceptionnaire)",
            "permissions": {"scanner", "voir_siens"},
            "types_scan_autorises": ["BL"],
        },
        "comptable": {
            "label": "Comptable",
            "permissions": {"scanner", "voir_siens", "voir_tous", "resynchroniser"},
            "types_scan_autorises": ["BL", "FACTURE"],
        },
        "responsable": {
            "label": "Responsable",
            "permissions": {"scanner", "voir_siens", "voir_tous", "remplacer", "supprimer", "resynchroniser", "voir_audit"},
            "types_scan_autorises": ["BL", "FACTURE"],
        },
        "lecteur": {
            "label": "Lecteur",
            "permissions": {"voir_tous", "voir_audit"},
            "types_scan_autorises": [],
        },
        "admin": {
            "label": "Administrateur",
            "permissions": {"scanner", "voir_siens", "voir_tous", "remplacer", "supprimer", "resynchroniser", "voir_audit", "gerer_utilisateurs"},
            "types_scan_autorises": ["BL", "FACTURE"],
        },
    },
    "urium": {
        "magasinier": {
            "label": "Magasinier",
            "permissions": {"scanner", "voir_siens", "generer_br"},
            "types_scan_autorises": ["BL"],
        },
        "achats": {
            "label": "Service achats",
            "permissions": {"scanner", "voir_siens", "voir_tous", "generer_br"},
            "types_scan_autorises": ["BL", "FACTURE"],
        },
        "directeur": {
            "label": "Directeur",
            "permissions": {"scanner", "voir_siens", "voir_tous", "remplacer", "supprimer", "resynchroniser", "voir_audit", "generer_br", "annuler_br"},
            "types_scan_autorises": ["BL", "FACTURE"],
        },
        "admin": {
            "label": "Administrateur",
            "permissions": {"scanner", "voir_siens", "voir_tous", "remplacer", "supprimer", "resynchroniser", "voir_audit", "gerer_utilisateurs", "generer_br", "annuler_br"},
            "types_scan_autorises": ["BL", "FACTURE"],
        },
    },
}


def get_role_definition(erp_type: str, role: str) -> dict:
    """Retourne la définition d'un rôle ou lève ValueError."""
    try:
        return ROLES[erp_type][role]
    except KeyError:
        raise ValueError(f"Rôle '{role}' inconnu pour l'ERP '{erp_type}'.")


def has_permission(erp_type: str, role: str, permission: str) -> bool:
    """Vérifie si un rôle possède une permission donnée."""
    defn = get_role_definition(erp_type, role)
    return permission in defn["permissions"]


def can_scan_type(erp_type: str, role: str, type_document: str) -> bool:
    """Vérifie si un rôle peut scanner un type de document donné."""
    defn = get_role_definition(erp_type, role)
    return type_document in defn["types_scan_autorises"]
