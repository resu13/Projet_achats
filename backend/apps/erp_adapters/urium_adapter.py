"""Adaptateur Urium, en attente du contrat d’accès à l’ERP."""
from __future__ import annotations

import logging
from typing import Any
from . import ErpAdaptateurBase, ErpIndisponibleError

logger = logging.getLogger(__name__)


class AdaptateurUrium(ErpAdaptateurBase):
    """Adaptateur à connecter une fois le mode d’accès Urium défini."""

    def __init__(self):
        pass

    # ── Interface obligatoire ─────────────────────────────────────────────────

    def rechercher_bc(self, criteres: dict) -> list[dict]:
        raise ErpIndisponibleError(
            "Le connecteur Urium n’est pas configuré : aucune donnée de démonstration n’est renvoyée."
        )

    def lire_bc(self, reference: str) -> dict | None:
        raise ErpIndisponibleError(
            "Le connecteur Urium n’est pas configuré : aucune donnée de démonstration n’est renvoyée."
        )

    def verifier_connexion(self) -> None:
        raise ErpIndisponibleError(
            "Le connecteur Urium n’est pas configuré. La recherche de BC et la lecture des lignes sont indisponibles."
        )

    def lister_br_erp(self, bc: Any) -> list[dict]:
        """
        Pour Urium, les BR sont générés par l'application elle-même.
        Cette méthode retourne les BR locaux associés au BC.
        """
        from apps.reception.models import BonReception
        brs = BonReception.objects.filter(
            bon_commande=bc,
            statut__in=["valide", "annule"],
        ).order_by("valide_le")
        return [
            {
                "reference_erp": br.numero,
                "date_document": br.valide_le.date() if br.valide_le else None,
                "statut_erp": br.statut,
                "detail": {
                    "numero_bl_fournisseur": br.numero_bl_fournisseur,
                    "valide_par": br.nom_receptionnaire,
                },
            }
            for br in brs
        ]

    def pousser_document(self, scan: Any) -> None:
        """
        Urium ne reçoit pas les liens Drive.
        Le statut sera défini sur "non_applicable" par le pipeline de scan.
        Cette méthode ne fait rien.
        """
        # Le pipeline appelant est responsable de mettre statut_sync = "non_applicable"
        pass

    def pousser_reception(self, bon_reception: Any) -> None:
        """
        Export optionnel d'un BR validé vers Urium.
        Vide par défaut — à implémenter quand Urium fournira une interface d'import.
        """
        logger.info(
            "pousser_reception : pas encore implémenté pour Urium (BR %s).",
            getattr(bon_reception, "numero", "?"),
        )
