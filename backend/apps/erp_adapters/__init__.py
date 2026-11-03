"""
Adaptateur ERP — Interface commune et fabrique.

Pattern Adapter : toute la logique métier du backend appelle uniquement
get_adaptateur() et l'interface ErpAdaptateurBase. Aucune logique
spécifique à un ERP n'apparaît en dehors de ce module.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any
from django.conf import settings

logger = logging.getLogger(__name__)


# ─── Interface commune ────────────────────────────────────────────────────────

class ErpAdaptateurBase(ABC):
    """
    Interface que TOUS les adaptateurs ERP doivent implémenter.
    Méthodes obligatoires : rechercher_bc, lire_bc, lister_br_erp, pousser_document.
    """

    @abstractmethod
    def rechercher_bc(self, criteres: dict) -> list[dict]:
        """
        Recherche des bons de commande.
        criteres : {
            "reference": str | None,
            "fournisseur": str | None,
            "date_debut": date | None,
            "date_fin": date | None,
        }
        Retourne : liste de dicts {reference, fournisseur, date, statut_erp, erp_id, ...}
        """

    @abstractmethod
    def lire_bc(self, reference: str) -> dict | None:
        """
        Retourne les détails complets d'un BC.
        Pour Urium, inclut aussi les lignes de commande.
        Retourne None si introuvable.
        Format : {
            "reference": str,
            "fournisseur": str,
            "date": date,
            "statut_erp": str,
            "erp_id": str,
            "montant": Decimal | None,
            "devise": str,
            "lignes": [  # Urium uniquement
                {"code_article": str, "designation": str, "unite": str, "quantite_commandee": Decimal}
            ]
        }
        """

    @abstractmethod
    def lister_br_erp(self, bc: Any) -> list[dict]:
        """
        Liste les bons de réception liés à un BC.
        bc : instance BonCommande (accès à bc.reference et bc.erp_id)
        Retourne : liste de dicts {reference_erp, date_document, statut_erp, detail}
        """

    @abstractmethod
    def pousser_document(self, scan: Any) -> None:
        """
        Pousse le lien Drive d'un document scanné vers l'ERP.
        scan : instance DocumentScan
        Peut lever ErpIndisponibleError ou ErpErreurError.
        Pour Urium, cette méthode doit définir scan.statut_sync = "non_applicable".
        """

    @abstractmethod
    def verifier_connexion(self) -> None:
        """Vérifie la connexion à l’ERP sans modifier de données."""


# ─── Exceptions ERP ──────────────────────────────────────────────────────────

class ErpIndisponibleError(Exception):
    """L'ERP est inaccessible (réseau, authentification)."""

class ErpErreurError(Exception):
    """L'ERP a répondu mais avec une erreur métier."""

class BcIntrouvableError(Exception):
    """Le BC demandé n'existe pas dans l'ERP."""


# ─── Fabrique ─────────────────────────────────────────────────────────────────

def get_adaptateur() -> ErpAdaptateurBase:
    """
    Retourne l'adaptateur correspondant à ERP_TYPE défini dans le .env.
    C'est le SEUL endroit où l'on sélectionne l'implémentation.
    """
    erp_type = getattr(settings, "ERP_TYPE", "").lower()
    if erp_type == "odoo":
        from .odoo_adapter import AdaptateurOdoo
        return AdaptateurOdoo()
    elif erp_type == "urium":
        from .urium_adapter import AdaptateurUrium
        return AdaptateurUrium()
    else:
        raise ValueError(
            f"ERP_TYPE='{erp_type}' non reconnu. Valeurs acceptées : 'odoo', 'urium'."
        )
