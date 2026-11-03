"""
Pipeline de traitement d'un scan — logique métier principale.

Ordre d'exécution :
  1. Valider le fichier (MIME réel, taille)
  2. Vérifier l'absence de doublon
  3. Vérifier la permission de scanner ce type de document
  4. Créer ou retrouver le dossier Drive BC/<reference>/<type>
  5. Uploader le fichier sur Drive
  6. Enregistrer le DocumentScan en base (statut = en_attente)
  7. Appeler l'adaptateur ERP (pousser_document)
  8. Mettre à jour le statut (synchronisé | non_applicable | échec)
  9. Journaliser

Si l'adaptateur ERP échoue, le scan est conservé avec statut="échec".
Il peut être relancé via l'action "resynchroniser".
"""
from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.utils import timezone

from apps.documents.models import BonCommande, DocumentScan, JournalActivite
from apps.erp_adapters import get_adaptateur, ErpIndisponibleError, ErpErreurError
from services.drive_service import (
    get_drive_service,
    valider_fichier,
    FichierInvalideError,
    DriveIndisponibleError,
)

if TYPE_CHECKING:
    from apps.accounts.models import Utilisateur

logger = logging.getLogger(__name__)


class DoublonDocumentError(Exception):
    """Un document identique existe déjà pour ce BC."""

class PermissionTypeError(Exception):
    """L'utilisateur n'est pas autorisé à scanner ce type de document."""


def traiter_scan(
    utilisateur: "Utilisateur",
    bon_commande: BonCommande,
    type_document: str,
    numero_document: str,
    nom_fichier: str,
    contenu: bytes,
    bons_commande: list[BonCommande] | None = None,
) -> DocumentScan:
    """
    Traite un scan de bout en bout.
    Lève FichierInvalideError, DoublonDocumentError, PermissionTypeError,
    DriveIndisponibleError selon l'étape qui échoue.
    """

    # ── Étape 1 : Validation fichier ─────────────────────────────────────────
    mime_type = valider_fichier(contenu, nom_fichier)

    # ── Étape 2 : Vérification permission par type ────────────────────────────
    membre = utilisateur.membre
    if not membre.peut_scanner_type(type_document):
        raise PermissionTypeError(
            f"Vous n'êtes pas autorisé à scanner des documents de type '{type_document}'."
        )

    # ── Étape 3 : Vérification doublon ────────────────────────────────────────
    associations = bons_commande or [bon_commande]
    if DocumentScan.objects.filter(
        Q(bon_commande__in=associations) | Q(bons_commande_lies__in=associations)
    ).filter(
        type_document=type_document,
        numero_document=numero_document,
    ).distinct().exists():
        raise DoublonDocumentError(
            f"Un document '{type_document}' avec le numéro '{numero_document}' "
            "existe déjà pour l'un des bons de commande sélectionnés."
        )

    # ── Étapes 4 & 5 : Drive ─────────────────────────────────────────────────
    drive = get_drive_service()
    dossier_id = drive.obtenir_dossier_bc(bon_commande.reference, type_document)
    file_id, drive_link = drive.uploader_fichier(contenu, nom_fichier, mime_type, dossier_id)

    # ── Étape 6 : Enregistrement en base ─────────────────────────────────────
    try:
        with transaction.atomic():
            scan = DocumentScan.objects.create(
                bon_commande=bon_commande,
                type_document=type_document,
                numero_document=numero_document,
                nom_fichier=nom_fichier,
                drive_file_id=file_id,
                drive_link=drive_link,
                statut_sync=DocumentScan.STATUT_EN_ATTENTE,
                cree_par=utilisateur,
            )
            scan.bons_commande_lies.set(associations)
    except Exception:
        try:
            drive.supprimer_fichier(file_id)
        except Exception as cleanup_error:
            logger.error(
                "Échec du nettoyage du fichier Drive %s après erreur de persistance du scan (%s).",
                file_id,
                type(cleanup_error).__name__,
            )
        raise

    # ── Étapes 7 & 8 : Adaptateur ERP ────────────────────────────────────────
    erp_type = getattr(settings, "ERP_TYPE", "")
    if erp_type == "urium":
        # Urium ne reçoit pas les liens Drive
        scan.statut_sync = DocumentScan.STATUT_NON_APPLICABLE
        scan.save(update_fields=["statut_sync"])
    else:
        try:
            adaptateur = get_adaptateur()
            adaptateur.pousser_document(scan)
            scan.statut_sync = DocumentScan.STATUT_SYNCHRONISE
            scan.message_erreur = ""
            scan.save(update_fields=["statut_sync", "message_erreur"])
        except (ErpIndisponibleError, ErpErreurError) as exc:
            logger.warning(
                "Échec synchronisation ERP pour scan %s : %s",
                scan.pk,
                type(exc).__name__,
            )
            scan.statut_sync = DocumentScan.STATUT_ECHEC
            scan.message_erreur = "Synchronisation ERP en attente. Utilisez 'Resynchroniser'."
            scan.save(update_fields=["statut_sync", "message_erreur"])

    # ── Étape 9 : Journal ────────────────────────────────────────────────────
    return scan


def resynchroniser_scan(scan: DocumentScan, utilisateur: "Utilisateur") -> DocumentScan:
    """
    Relance la synchronisation ERP d'un scan en échec.
    Idempotent : sans effet si déjà synchronisé.
    """
    if scan.statut_sync == DocumentScan.STATUT_SYNCHRONISE:
        return scan

    try:
        adaptateur = get_adaptateur()
        adaptateur.pousser_document(scan)
        scan.statut_sync = DocumentScan.STATUT_SYNCHRONISE
        scan.message_erreur = ""
    except (ErpIndisponibleError, ErpErreurError) as exc:
        logger.warning(
            "Échec de reprise ERP pour scan %s : %s",
            scan.pk,
            type(exc).__name__,
        )
        scan.statut_sync = DocumentScan.STATUT_ECHEC
        scan.message_erreur = "Resynchronisation échouée. L'ERP est peut-être indisponible."

    scan.save(update_fields=["statut_sync", "message_erreur"])

    JournalActivite.objects.create(
        utilisateur=utilisateur,
        action=JournalActivite.ACTION_RESYNC,
        bon_commande=scan.bon_commande,
        detail=f"Resynchronisation scan #{scan.pk} ({scan.type_document} {scan.numero_document}) — statut : {scan.statut_sync}",
    )
    return scan
