"""
AdaptateurOdoo — Implémentation XML-RPC pour l'ERP Odoo.

Accès : clé API Odoo (utilisateur technique dédié, permissions minimales).
Modèles Odoo utilisés :
  - purchase.order  → BonCommande
  - stock.picking   → DocumentErp (réceptions/BR)
  - ir.attachment   → pièce jointe URL pointant vers Drive
  - mail.message    → message dans le chatter

SÉCURITÉ :
  - Liste blanche des modèles Odoo autorisés.
  - Aucun secret n'est loggé.
  - Toutes les exceptions Odoo sont converties en ErpIndisponibleError ou ErpErreurError.
"""
from __future__ import annotations

import logging
import xmlrpc.client
from functools import lru_cache
from typing import Any
from django.conf import settings

from . import ErpAdaptateurBase, ErpIndisponibleError, ErpErreurError, BcIntrouvableError

logger = logging.getLogger(__name__)

# Liste blanche des modèles Odoo que l'adaptateur peut toucher
MODELES_AUTORISES = frozenset([
    "purchase.order",
    "stock.picking",
    "ir.attachment",
    "mail.message",
    "res.partner",
])

# Table de correspondance type_document → modèle Odoo cible pour ir.attachment
MODELE_CIBLE = {
    "BL": "purchase.order",
    "FACTURE": "purchase.order",
}


def _verifier_modele(modele: str) -> None:
    if modele not in MODELES_AUTORISES:
        raise ValueError(f"Modèle Odoo '{modele}' non autorisé.")


class AdaptateurOdoo(ErpAdaptateurBase):
    """Adaptateur Odoo via XML-RPC externe."""

    def __init__(self):
        self._url = settings.ODOO_URL.rstrip("/")
        self._db = settings.ODOO_DB
        self._user = settings.ODOO_USER
        self._key = settings.ODOO_KEY
        self._uid: int | None = None
        if not all((self._url, self._db, self._user, self._key)):
            raise ErpIndisponibleError(
                "La connexion Odoo n’est pas configurée. Vérifiez ODOO_URL, ODOO_DB, ODOO_USER et ODOO_KEY."
            )

    # ── Connexion ────────────────────────────────────────────────────────────

    def _get_uid(self) -> int:
        """Authentifie et retourne l'UID de l'utilisateur technique."""
        if self._uid:
            return self._uid
        try:
            common = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/common")
            uid = common.authenticate(self._db, self._user, self._key, {})
            if not uid:
                raise ErpIndisponibleError("Authentification Odoo échouée.")
            self._uid = uid
            return uid
        except ErpIndisponibleError:
            raise
        except Exception as exc:
            logger.error("Connexion Odoo impossible : %s", type(exc).__name__)
            raise ErpIndisponibleError("L'ERP Odoo est inaccessible.") from exc

    def verifier_connexion(self) -> None:
        self._get_uid()

    def _execute(self, model: str, method: str, *args, **kwargs) -> Any:
        """Exécute un appel XML-RPC sur l'objet models."""
        _verifier_modele(model)
        uid = self._get_uid()
        try:
            models = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/object")
            return models.execute_kw(self._db, uid, self._key, model, method, args, kwargs)
        except xmlrpc.client.Fault as exc:
            logger.warning("Erreur Odoo (Fault) sur %s.%s : %s", model, method, exc.faultCode)
            raise ErpErreurError(f"Erreur ERP lors de l'opération '{method}' sur '{model}'.") from exc
        except Exception as exc:
            logger.error("Erreur réseau Odoo sur %s.%s : %s", model, method, type(exc).__name__)
            raise ErpIndisponibleError("L'ERP Odoo est inaccessible.") from exc

    # ── Interface ────────────────────────────────────────────────────────────

    def rechercher_bc(self, criteres: dict) -> list[dict]:
        domaine = [("state", "in", ["purchase", "done"])]

        if criteres.get("reference"):
            domaine.append(("name", "ilike", criteres["reference"]))
        if criteres.get("fournisseur"):
            domaine.append(("partner_id.name", "ilike", criteres["fournisseur"]))
        if criteres.get("date_debut"):
            domaine.append(("date_order", ">=", str(criteres["date_debut"])))
        if criteres.get("date_fin"):
            domaine.append(("date_order", "<=", str(criteres["date_fin"])))

        try:
            records = self._execute(
                "purchase.order", "search_read",
                domaine,
                fields=["name", "partner_id", "date_order", "state", "amount_total", "currency_id"],
                limit=200,
                order="date_order desc",
            )
        except (ErpIndisponibleError, ErpErreurError):
            raise

        return [self._format_bc(r) for r in records]

    def lire_bc(self, reference: str) -> dict | None:
        try:
            records = self._execute(
                "purchase.order", "search_read",
                [("name", "=", reference)],
                fields=["name", "partner_id", "date_order", "state", "amount_total",
                        "currency_id", "id"],
                limit=1,
            )
        except (ErpIndisponibleError, ErpErreurError):
            raise

        if not records:
            return None
        return self._format_bc(records[0])

    def lister_br_erp(self, bc: Any) -> list[dict]:
        """Retourne les stock.picking (réceptions) liées au BC."""
        if not bc.erp_id:
            return []
        try:
            records = self._execute(
                "stock.picking", "search_read",
                [
                    ("purchase_id", "=", int(bc.erp_id)),
                    ("picking_type_code", "=", "incoming"),
                ],
                fields=["name", "scheduled_date", "state", "origin"],
                limit=100,
            )
        except (ErpIndisponibleError, ErpErreurError):
            raise

        return [
            {
                "reference_erp": r["name"],
                "date_document": r.get("scheduled_date", "")[:10] if r.get("scheduled_date") else None,
                "statut_erp": r.get("state", ""),
                "detail": {"origin": r.get("origin", "")},
            }
            for r in records
        ]

    def pousser_document(self, scan: Any) -> None:
        """
        Crée une pièce jointe URL dans Odoo et poste un message dans le chatter.
        Le scan doit avoir : bon_commande.erp_id, type_document, numero_document,
        drive_link, et l'utilisateur créateur.
        """
        modele_cible = MODELE_CIBLE.get(scan.type_document, "purchase.order")
        nom_piece = f"{scan.type_document}_{scan.numero_document}"
        nom_utilisateur = scan.cree_par.get_full_name() or scan.cree_par.username
        bons_commande = scan.bons_commande_associes

        try:
            for bc in bons_commande:
                if not bc.erp_id:
                    raise ErpErreurError(
                        f"L'identifiant ERP du BC {bc.reference} est manquant."
                    )
                try:
                    erp_id = int(bc.erp_id)
                except (TypeError, ValueError) as exc:
                    raise ErpErreurError(
                        f"L'identifiant ERP du BC {bc.reference} est invalide."
                    ) from exc

                existing_attachments = self._execute(
                    "ir.attachment", "search_read",
                    [
                        ("res_model", "=", modele_cible),
                        ("res_id", "=", erp_id),
                        ("url", "=", scan.drive_link),
                    ],
                    fields=["id"],
                    limit=1,
                )
                if not existing_attachments:
                    self._execute(
                        "ir.attachment", "create",
                        {
                            "name": nom_piece,
                            "type": "url",
                            "url": scan.drive_link,
                            "res_model": modele_cible,
                            "res_id": erp_id,
                            "description": (
                                f"Document scanné par l'application achats. "
                                f"Type : {scan.type_document}, N° : {scan.numero_document}."
                            ),
                        },
                    )

                message_body = (
                    f"<p><b>Document scanné via l'application achats</b><br/>"
                    f"Type : {scan.type_document}<br/>"
                    f"N° document : {scan.numero_document}<br/>"
                    f"Scanné par : {nom_utilisateur}<br/>"
                    f"Lien Drive : <a href=\"{scan.drive_link}\">{scan.drive_link}</a></p>"
                )
                existing_messages = self._execute(
                    "mail.message", "search_read",
                    [
                        ("model", "=", "purchase.order"),
                        ("res_id", "=", erp_id),
                        ("message_type", "=", "comment"),
                        ("body", "=", message_body),
                    ],
                    fields=["id"],
                    limit=1,
                )
                if not existing_messages:
                    self._execute(
                        "mail.message", "create",
                        {
                            "model": "purchase.order",
                            "res_id": erp_id,
                            "message_type": "comment",
                            "subtype_id": 1,
                            "body": message_body,
                        },
                    )
        except (ErpIndisponibleError, ErpErreurError):
            raise

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _format_bc(record: dict) -> dict:
        partenaire = record.get("partner_id")
        fournisseur = partenaire[1] if isinstance(partenaire, (list, tuple)) else str(partenaire or "")
        devise_info = record.get("currency_id")
        devise = devise_info[1] if isinstance(devise_info, (list, tuple)) else "MAD"
        date_raw = record.get("date_order", "")
        date_str = date_raw[:10] if date_raw else None
        return {
            "reference": record.get("name", ""),
            "fournisseur": fournisseur,
            "date": date_str,
            "statut_erp": record.get("state", ""),
            "erp_id": str(record.get("id", "")),
            "montant": record.get("amount_total"),
            "devise": devise,
            "lignes": [],  # Odoo : lignes non utilisées côté application
        }
