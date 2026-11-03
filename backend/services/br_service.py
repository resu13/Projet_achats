"""
Service de validation d'un Bon de Réception (Urium).

Garanties :
  - Atomicité et idempotence : un double clic ou deux requêtes simultanées
    ne produisent qu'un seul BR validé avec un seul numéro.
  - Numérotation sans trou : SELECT FOR UPDATE sur CompteurBR.
  - Immuabilité : après validation, aucun champ du BR ne peut être modifié.
  - Empreinte SHA-256 du PDF calculée et stockée.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date

from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

from apps.documents.models import BonCommande, JournalActivite
from apps.reception.models import BonReception, LigneReception, CompteurBR
from services.pdf_service import generer_pdf_br
from services.drive_service import get_drive_service, DriveIndisponibleError

logger = logging.getLogger(__name__)


class ValidationBRError(Exception):
    """Erreur métier lors de la validation d'un BR."""

class ReauthEchecError(Exception):
    """Mot de passe incorrect lors de la ré-authentification."""

class QuantiteInvalideError(Exception):
    """Quantité reçue invalide (nulle, négative ou excédentaire)."""


def valider_bon_reception(
    bon_reception: BonReception,
    utilisateur,
    adresse_ip: str,
    mot_de_passe: str | None = None,
) -> BonReception:
    """
    Valide un BR en brouillon de façon atomique et idempotente.

    Paramètres :
      - bon_reception : instance BonReception (doit être en brouillon)
      - utilisateur   : utilisateur connecté (doit avoir la permission generer_br)
      - adresse_ip    : adresse IP du client
      - mot_de_passe  : requis si REAUTH_VALIDATION_BR=True
    """
    from django.conf import settings

    # ── Ré-authentification optionnelle ──────────────────────────────────────
    if getattr(settings, "REAUTH_VALIDATION_BR", False):
        if not mot_de_passe:
            raise ReauthEchecError("Le mot de passe est requis pour valider la réception.")
        user_reauth = authenticate(username=utilisateur.username, password=mot_de_passe)
        if user_reauth is None or user_reauth.pk != utilisateur.pk:
            raise ReauthEchecError("Mot de passe incorrect.")

    with transaction.atomic():
        # ── SELECT FOR UPDATE — idempotence ───────────────────────────────────
        br = BonReception.objects.select_for_update().get(pk=bon_reception.pk)

        if br.statut == BonReception.STATUT_VALIDE:
            # Déjà validé (double clic ou double requête) — retourner l'existant
            return br

        if br.statut != BonReception.STATUT_BROUILLON:
            raise ValidationBRError(
                f"Ce bon de réception ne peut pas être validé (statut : {br.statut})."
            )

        # ── Vérifications des quantités ───────────────────────────────────────
        _verifier_quantites(br)

        # ── Numérotation séquentielle atomique ────────────────────────────────
        annee = date.today().year
        numero = CompteurBR.prochain_numero(annee)

        # ── Enregistrement des champs de validation ───────────────────────────
        membre = utilisateur.membre
        br.numero = numero
        br.statut = BonReception.STATUT_VALIDE
        br.valide_par = utilisateur
        br.valide_le = timezone.now()
        br.nom_receptionnaire = (
            f"{utilisateur.get_full_name() or utilisateur.username} "
            f"({membre.role})"
        )
        br.adresse_ip_validation = adresse_ip

        # ── Génération du PDF ─────────────────────────────────────────────────
        pdf_bytes = generer_pdf_br(br)
        br.empreinte_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

        # ── Upload Drive ──────────────────────────────────────────────────────
        drive = get_drive_service()
        dossier_id = drive.obtenir_dossier_bc(br.bon_commande.reference, "BR")
        nom_fichier = f"{numero}.pdf"
        file_id, drive_link = drive.uploader_fichier(pdf_bytes, nom_fichier, "application/pdf", dossier_id)
        br.drive_file_id = file_id
        br.drive_link = drive_link

        br.save()

        # ── Journal ───────────────────────────────────────────────────────────
        JournalActivite.objects.create(
            utilisateur=utilisateur,
            action=JournalActivite.ACTION_VALIDATION_BR,
            bon_commande=br.bon_commande,
            detail=(
                f"BR {numero} validé par {br.nom_receptionnaire}, "
                f"IP : {adresse_ip}, SHA-256 : {br.empreinte_sha256[:16]}…"
            ),
        )

    return br


def annuler_bon_reception(
    bon_reception: BonReception,
    utilisateur,
    motif: str,
) -> BonReception:
    """
    Annule un BR validé. Motif obligatoire.
    Le BR reste visible, ses quantités sont retirées des totaux.
    """
    if not motif or not motif.strip():
        raise ValidationBRError("Le motif d'annulation est obligatoire.")

    if bon_reception.statut != BonReception.STATUT_VALIDE:
        raise ValidationBRError(
            f"Seul un BR validé peut être annulé (statut actuel : {bon_reception.statut})."
        )

    with transaction.atomic():
        br = BonReception.objects.select_for_update().get(pk=bon_reception.pk)
        if br.statut != BonReception.STATUT_VALIDE:
            raise ValidationBRError("Ce BR a déjà été annulé ou modifié.")
        br.statut = BonReception.STATUT_ANNULE
        br.motif_annulation = motif.strip()
        br.save(update_fields=["statut", "motif_annulation"])

        JournalActivite.objects.create(
            utilisateur=utilisateur,
            action=JournalActivite.ACTION_ANNULATION_BR,
            bon_commande=br.bon_commande,
            detail=f"Annulation du BR {br.numero}. Motif : {motif[:200]}",
        )

    return br


def _verifier_quantites(br: BonReception) -> None:
    """Vérifie que toutes les lignes ont des quantités valides."""
    line_ids = br.lignes.values_list("ligne_bon_commande_id", flat=True)
    list(br.bon_commande.lignes.select_for_update().filter(pk__in=line_ids))
    receipt_lines = br.lignes.select_related("ligne_bon_commande").all()
    if not receipt_lines.exists():
        raise QuantiteInvalideError("Le bon de réception doit contenir au moins une ligne.")
    for ligne in receipt_lines:
        if ligne.quantite_recue <= 0:
            raise QuantiteInvalideError(
                f"La quantité reçue pour '{ligne.ligne_bon_commande.designation}' "
                f"doit être supérieure à zéro."
            )
        remaining = ligne.ligne_bon_commande.reste_a_recevoir
        if ligne.quantite_recue > remaining:
            raise QuantiteInvalideError(
                f"La quantité reçue pour '{ligne.ligne_bon_commande.designation}' "
                f"dépasse le reste à recevoir ({remaining})."
            )
