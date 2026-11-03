from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import BonCommande, JournalActivite
from apps.reception.models import BonReception, LigneBonCommande, LigneReception
from services.br_service import (
    QuantiteInvalideError,
    ReauthEchecError,
    ValidationBRError,
    annuler_bon_reception,
    valider_bon_reception,
)
from services.drive_service import DriveIndisponibleError, get_drive_service


def _error(message, code):
    return Response({"message": message}, status=code)


def _payload(receipt):
    return {
        "id": receipt.pk,
        "reference": receipt.numero or f"BR-BROUILLON-{receipt.pk}",
        "bcId": receipt.bon_commande_id,
        "statut": receipt.statut,
        "lignes": [
            {
                "ligneId": line.ligne_bon_commande_id,
                "article": line.ligne_bon_commande.designation,
                "quantite": float(line.quantite_recue),
            }
            for line in receipt.lignes.select_related("ligne_bon_commande").order_by(
                "ligne_bon_commande__ordre", "pk"
            )
        ],
        "numeroBl": receipt.numero_bl_fournisseur,
        "remarques": receipt.remarques,
        "dateReception": receipt.date_reception.isoformat(),
        "motifAnnulation": receipt.motif_annulation,
    }


def _permission_error(user, permission):
    if settings.ERP_TYPE.lower() != "urium":
        return _error("Les bons de réception ne sont disponibles que pour Urium.", status.HTTP_404_NOT_FOUND)
    if not user.membre.has_perm_app(permission):
        return _error(f"Permission '{permission}' requise.", status.HTTP_403_FORBIDDEN)
    return None


def _parse_receipt_lines(order, raw_lines):
    if not isinstance(raw_lines, list):
        raise ValueError("La liste des lignes de réception est invalide.")
    parsed = []
    seen = set()
    for raw in raw_lines:
        if not isinstance(raw, dict):
            raise ValueError("Une ligne de réception est invalide.")
        line_id = raw.get("ligneId")
        article = str(raw.get("article") or "").strip()
        if line_id is not None:
            if isinstance(line_id, bool) or not isinstance(line_id, int):
                raise ValueError("L’identifiant d’une ligne de BC est invalide.")
            line = LigneBonCommande.objects.filter(
                pk=line_id, bon_commande=order, actif=True
            ).first()
        else:
            matches = list(
                LigneBonCommande.objects.filter(
                    bon_commande=order,
                    actif=True,
                    designation=article,
                )[:2]
            )
            if len(matches) > 1:
                raise ValueError(
                    f"Plusieurs lignes portent la désignation « {article} » ; l’identifiant de ligne est requis."
                )
            line = matches[0] if matches else None
        if line is None:
            raise ValueError("Une ligne ne correspond pas à ce bon de commande.")
        if line.pk in seen:
            raise ValueError("Une ligne du bon de commande ne peut apparaître qu’une fois.")
        seen.add(line.pk)
        try:
            quantity = Decimal(str(raw.get("quantite")))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Une quantité reçue est invalide.") from exc
        if not quantity.is_finite() or quantity < 0:
            raise ValueError("Les quantités doivent être des nombres positifs ou nuls.")
        if quantity > line.reste_a_recevoir:
            raise ValueError(
                f"La quantité reçue dépasse le reste à recevoir pour « {line.designation} »."
            )
        parsed.append((line, quantity))
    return parsed


def _save_lines(receipt, raw_lines):
    lines = _parse_receipt_lines(receipt.bon_commande, raw_lines)
    receipt.lignes.all().delete()
    LigneReception.objects.bulk_create([
        LigneReception(
            bon_reception=receipt,
            ligne_bon_commande=line,
            quantite_recue=quantity,
        )
        for line, quantity in lines
    ])


@transaction.atomic
def _update_receipt(receipt, data):
    if "lignes" in data:
        _save_lines(receipt, data["lignes"])
    if "numeroBl" in data:
        receipt.numero_bl_fournisseur = str(data["numeroBl"] or "").strip()[:100]
    if "remarques" in data:
        receipt.remarques = str(data["remarques"] or "").strip()
    if "dateReception" in data:
        try:
            receipt.date_reception = date.fromisoformat(str(data["dateReception"]))
        except ValueError as exc:
            raise ValueError("La date de réception est invalide.") from exc
    receipt.save()


class ReceiptCreateContractView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        denied = _permission_error(request.user, "generer_br")
        if denied:
            return denied
        order = get_object_or_404(BonCommande, pk=order_id)
        try:
            if "lignes" in request.data and not isinstance(request.data["lignes"], list):
                raise ValueError("La liste des lignes de réception est invalide.")
            with transaction.atomic():
                receipt = BonReception.objects.create(
                    bon_commande=order,
                    cree_par=request.user,
                    numero_bl_fournisseur=str(request.data.get("numeroBl") or "").strip()[:100],
                    remarques=str(request.data.get("remarques") or "").strip(),
                )
                _update_receipt(receipt, request.data)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        JournalActivite.objects.create(
            utilisateur=request.user,
            action=JournalActivite.ACTION_CREATION_BR,
            bon_commande=order,
            detail=f"Création du brouillon de BR #{receipt.pk}.",
        )
        return Response(_payload(receipt), status=status.HTTP_201_CREATED)


class ReceiptDetailContractView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_receipt(self, request, receipt_id, permission="generer_br"):
        denied = _permission_error(request.user, permission)
        if denied:
            return None, denied
        receipt = get_object_or_404(
            BonReception.objects.prefetch_related("lignes__ligne_bon_commande"),
            pk=receipt_id,
        )
        return receipt, None

    def get(self, request, receipt_id):
        receipt, denied = self._get_receipt(request, receipt_id)
        if denied:
            return denied
        return Response(_payload(receipt))

    def patch(self, request, receipt_id):
        receipt, denied = self._get_receipt(request, receipt_id)
        if denied:
            return denied
        if receipt.statut != BonReception.STATUT_BROUILLON:
            return _error("Seul un brouillon peut être modifié.", status.HTTP_409_CONFLICT)
        try:
            _update_receipt(receipt, request.data)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        return Response(_payload(receipt))


class ReceiptValidateContractView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, receipt_id):
        denied = _permission_error(request.user, "generer_br")
        if denied:
            return denied
        receipt = get_object_or_404(BonReception, pk=receipt_id)
        try:
            receipt = valider_bon_reception(
                receipt,
                utilisateur=request.user,
                adresse_ip=request.META.get("REMOTE_ADDR", ""),
                mot_de_passe=request.data.get("mot_de_passe"),
            )
        except (ReauthEchecError, QuantiteInvalideError, ValidationBRError) as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except DriveIndisponibleError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(_payload(receipt))


class ReceiptCancelContractView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, receipt_id):
        denied = _permission_error(request.user, "annuler_br")
        if denied:
            return denied
        receipt = get_object_or_404(BonReception, pk=receipt_id)
        try:
            receipt = annuler_bon_reception(
                receipt,
                utilisateur=request.user,
                motif=str(request.data.get("motif") or ""),
            )
        except ValidationBRError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        return Response(_payload(receipt))


class ReceiptPdfContractView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, receipt_id):
        if settings.ERP_TYPE.lower() != "urium":
            return _error("Les bons de réception ne sont disponibles que pour Urium.", status.HTTP_404_NOT_FOUND)
        denied = _permission_error(request.user, "generer_br")
        if denied:
            if request.user.membre.has_perm_app("voir_tous"):
                denied = None
            else:
                return denied
        receipt = get_object_or_404(BonReception, pk=receipt_id)
        if receipt.statut not in (BonReception.STATUT_VALIDE, BonReception.STATUT_ANNULE):
            return _error("Seul un bon de réception validé peut être téléchargé.", status.HTTP_409_CONFLICT)
        if not receipt.drive_file_id:
            return _error("Le PDF de ce bon de réception est indisponible.", status.HTTP_404_NOT_FOUND)
        try:
            content = get_drive_service().telecharger_fichier(receipt.drive_file_id)
        except DriveIndisponibleError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{receipt.numero}.pdf"'
        return response
