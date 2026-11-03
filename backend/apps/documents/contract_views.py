from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import BonCommande, DocumentErp, DocumentScan, JournalActivite
from apps.reception.models import BonReception, LigneBonCommande
from services.scan_pipeline import (
    DoublonDocumentError,
    PermissionTypeError,
    resynchroniser_scan,
    traiter_scan,
)
from services.drive_service import (
    DriveIndisponibleError,
    FichierInvalideError,
    get_drive_service,
    valider_fichier,
)
from apps.erp_adapters import ErpErreurError, ErpIndisponibleError, get_adaptateur


def _error(message: str, code: int) -> Response:
    return Response({"message": message}, status=code)


def _can_view_orders(user) -> bool:
    membre = user.membre
    return any(
        membre.has_perm_app(permission)
        for permission in ("voir_siens", "voir_tous", "scanner", "generer_br")
    )


def _sync_order(data: dict) -> BonCommande:
    reference = str(data.get("reference") or "").strip()
    if not reference:
        raise ValueError("L'ERP a retourné un bon de commande sans référence.")
    order_date = data.get("date") or None
    if isinstance(order_date, str) and order_date:
        order_date = date.fromisoformat(order_date[:10])
    order, _ = BonCommande.objects.update_or_create(
        reference=reference,
        defaults={
            "fournisseur": str(data.get("fournisseur") or ""),
            "date": order_date,
            "statut_erp": str(data.get("statut_erp") or ""),
            "montant": data.get("montant"),
            "devise": str(data.get("devise") or ""),
            "erp_id": str(data.get("erp_id") or ""),
        },
    )

    lines = data.get("lignes")
    if isinstance(lines, list) and lines:
        existing = list(
            LigneBonCommande.objects.filter(bon_commande=order).order_by("ordre", "pk")
        )
        unused_ids = {line.pk for line in existing}
        for line in existing:
            if line.actif:
                line.actif = False
                line.save(update_fields=["actif"])
        for index, raw_line in enumerate(lines):
            code = str(raw_line.get("code_article") or "")
            designation = str(raw_line.get("designation") or raw_line.get("article") or "")
            match = next(
                (
                    line for line in existing
                    if line.pk in unused_ids and (
                        (code and line.code_article == code)
                        or (not code and line.designation == designation)
                    )
                ),
                None,
            )
            values = {
                "code_article": code,
                "designation": designation,
                "unite": str(raw_line.get("unite") or ""),
                "quantite_commandee": Decimal(str(
                    raw_line.get("quantite_commandee", raw_line.get("commande", 0))
                )),
                "ordre": index,
                "actif": True,
            }
            if match:
                unused_ids.remove(match.pk)
                for field, value in values.items():
                    setattr(match, field, value)
                match.save(update_fields=list(values))
            else:
                LigneBonCommande.objects.create(bon_commande=order, **values)
    return order


def _scan_queryset_for_order(order: BonCommande):
    return DocumentScan.objects.filter(
        Q(bon_commande=order) | Q(bons_commande_lies=order)
    ).distinct()


def _order_payload(order: BonCommande, user=None, include_details: bool = False) -> dict:
    lines = [
        {
            "id": line.pk,
            "article": line.designation,
            "commande": float(line.quantite_commandee),
            "recue": float(line.quantite_deja_recue),
            "unite": line.unite,
        }
        for line in order.lignes.filter(actif=True)
    ]
    documents = _scan_queryset_for_order(order)
    if user is not None and not user.membre.has_perm_app("voir_tous"):
        documents = documents.filter(cree_par=user)
    delivery_notes = documents.filter(type_document=DocumentScan.TYPE_BL)
    invoices = documents.filter(type_document=DocumentScan.TYPE_FACTURE)
    receipts = BonReception.objects.filter(bon_commande=order)
    erp_receipts = DocumentErp.objects.filter(bon_commande=order, type_document="BR")
    received = sum(line["recue"] for line in lines)
    ordered = sum(line["commande"] for line in lines)
    if settings.ERP_TYPE == "urium":
        receipt_status = order.statut_reception or "non_recu"
        completeness = round(100 * received / ordered) if ordered else 0
    else:
        receipt_status = "non_recu"
        completeness = 50 * int(delivery_notes.exists()) + 50 * int(invoices.exists())

    payload = {
        "id": order.pk,
        "reference": order.reference,
        "fournisseur": order.fournisseur,
        "date": order.date.isoformat() if order.date else "",
        "statutErp": order.statut_erp,
        "montant": float(order.montant or 0),
        "devise": order.devise or "MAD",
        "statutReception": receipt_status,
        "completude": completeness,
        "lignes": lines,
        "br": receipts.filter(statut__in=[
            BonReception.STATUT_VALIDE, BonReception.STATUT_ANNULE
        ]).count() + erp_receipts.count(),
        "bl": delivery_notes.count(),
        "factures": invoices.count(),
    }

    if include_details:
        payload["documents"] = [_scan_payload(scan) for scan in documents.order_by("-cree_le")]
        payload["receptions"] = [
            {
                "id": receipt.pk,
                "reference": receipt.numero or f"BR-{receipt.pk}",
                "bcId": order.pk,
                "statut": receipt.statut,
                "lignes": [
                    {
                        "ligneId": line.ligne_bon_commande_id,
                        "article": line.ligne_bon_commande.designation,
                        "quantite": float(line.quantite_recue),
                    }
                    for line in receipt.lignes.select_related("ligne_bon_commande")
                ],
                "numeroBl": receipt.numero_bl_fournisseur,
                "remarques": receipt.remarques,
            }
            for receipt in receipts.order_by("-cree_le")
        ]
    return payload


def _scan_payload(scan: DocumentScan) -> dict:
    associated_orders = scan.bons_commande_associes
    payload = {
        "id": scan.pk,
        "type": scan.type_document,
        "numero": scan.numero_document,
        "fournisseur": scan.bon_commande.fournisseur,
        "bc": [order.reference for order in associated_orders],
        "bcIds": [order.pk for order in associated_orders],
        "statut": scan.statut_sync,
        "auteur": scan.cree_par.get_full_name() or scan.cree_par.username,
        "date": scan.cree_le.isoformat(),
        "driveLink": scan.drive_link,
    }
    if scan.message_erreur:
        payload["messageErreur"] = scan.message_erreur
    return payload


class PurchaseOrderListContractView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can_view_orders(request.user):
            return _error("Permission requise.", status.HTTP_403_FORBIDDEN)
        search = (request.query_params.get("recherche") or "").strip()
        supplier = (request.query_params.get("fournisseur") or "").strip()
        criteria = {
            "reference": search or None,
            "fournisseur": supplier or None,
            "date_debut": None,
            "date_fin": None,
        }
        period = request.query_params.get("periode")
        if period:
            try:
                criteria["date_debut"] = (date.today() - timedelta(days=int(period))).isoformat()
            except ValueError:
                return _error("La période doit être un nombre de jours.", status.HTTP_400_BAD_REQUEST)
        try:
            rows = get_adaptateur().rechercher_bc(criteria)
            orders = [_sync_order(row) for row in rows]
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except (ErpErreurError, ErpIndisponibleError) as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        data = [_order_payload(order, user=request.user) for order in orders]
        if request.query_params.get("incomplets") == "true":
            data = [order for order in data if order["completude"] < 100]
        return Response(data)


class PurchaseOrderDetailContractView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id: int):
        if not _can_view_orders(request.user):
            return _error("Permission requise.", status.HTTP_403_FORBIDDEN)
        order = get_object_or_404(BonCommande, pk=order_id)
        try:
            data = get_adaptateur().lire_bc(order.reference)
        except (ErpErreurError, ErpIndisponibleError) as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        if data is None:
            raise Http404("Bon de commande introuvable dans l'ERP.")
        order = _sync_order(data)
        return Response(_order_payload(order, user=request.user, include_details=True))


class ScanListContractView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membre = request.user.membre
        if not membre.has_perm_app("voir_siens") and not membre.has_perm_app("voir_tous"):
            return _error("Permission requise.", status.HTTP_403_FORBIDDEN)
        queryset = DocumentScan.objects.select_related(
            "bon_commande", "cree_par"
        ).prefetch_related("bons_commande_lies")
        if not membre.has_perm_app("voir_tous"):
            queryset = queryset.filter(cree_par=request.user)

        type_document = request.query_params.get("type")
        if type_document:
            queryset = queryset.filter(type_document=type_document)
        sync_status = request.query_params.get("statut")
        if sync_status:
            queryset = queryset.filter(statut_sync=sync_status)
        search = (request.query_params.get("recherche") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(numero_document__icontains=search)
                | Q(bon_commande__reference__icontains=search)
                | Q(bons_commande_lies__reference__icontains=search)
                | Q(bon_commande__fournisseur__icontains=search)
            )
        period = request.query_params.get("periode")
        if period:
            try:
                start = date.today() - timedelta(days=int(period))
            except ValueError:
                return _error("La période doit être un nombre de jours.", status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(cree_le__date__gte=start)
        scans = queryset.distinct().order_by("-cree_le")[:200]
        return Response([_scan_payload(scan) for scan in scans])

    def post(self, request):
        membre = request.user.membre
        if not membre.has_perm_app("scanner"):
            return _error("Permission de scan requise.", status.HTTP_403_FORBIDDEN)
        try:
            order_ids = request.data.get("ids_bc")
            if isinstance(order_ids, str):
                try:
                    order_ids = json.loads(order_ids)
                except json.JSONDecodeError:
                    return _error("La liste des bons de commande est invalide.", status.HTTP_400_BAD_REQUEST)
            if not isinstance(order_ids, list) or not order_ids:
                return _error("Sélectionnez au moins un bon de commande.", status.HTTP_400_BAD_REQUEST)
            if any(not isinstance(value, int) or isinstance(value, bool) for value in order_ids):
                return _error("La liste des bons de commande est invalide.", status.HTTP_400_BAD_REQUEST)
            if len(set(order_ids)) != len(order_ids):
                return _error("La liste des bons de commande contient un doublon.", status.HTTP_400_BAD_REQUEST)
            orders = list(BonCommande.objects.filter(pk__in=order_ids))
            if len(orders) != len(order_ids):
                return _error("Un bon de commande sélectionné est introuvable.", status.HTTP_404_NOT_FOUND)
            type_document = str(request.data.get("type") or "").strip().upper()
            numero = str(request.data.get("numero_document") or "").strip()
            fichier = request.FILES.get("fichier")
            if not type_document or not numero or not fichier:
                return _error("Le type, le numéro et le fichier sont obligatoires.", status.HTTP_400_BAD_REQUEST)
            if type_document not in (DocumentScan.TYPE_BL, DocumentScan.TYPE_FACTURE):
                return _error("Type de document invalide.", status.HTTP_400_BAD_REQUEST)
            if not membre.peut_scanner_type(type_document):
                return _error("Ce type de document n'est pas autorisé pour votre compte.", status.HTTP_403_FORBIDDEN)
            if DocumentScan.objects.filter(numero_document__iexact=numero).exists():
                return _error("Ce numéro de document existe déjà.", status.HTTP_409_CONFLICT)
            scan = traiter_scan(
                utilisateur=request.user,
                bon_commande=orders[0],
                bons_commande=orders,
                type_document=type_document,
                numero_document=numero,
                nom_fichier=fichier.name,
                contenu=fichier.read(),
            )
            JournalActivite.objects.create(
                utilisateur=request.user,
                action=JournalActivite.ACTION_SCAN,
                bon_commande=orders[0],
                detail=(
                    f"Création/traitement du scan {type_document} {numero} "
                    f"pour {', '.join(order.reference for order in orders)}"
                ),
            )
            return Response(_scan_payload(scan), status=status.HTTP_201_CREATED)
        except (FichierInvalideError, DoublonDocumentError, PermissionTypeError) as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except DriveIndisponibleError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)


class ScanDetailContractView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_scan(self, request, scan_id):
        scan = get_object_or_404(
            DocumentScan.objects.select_related("bon_commande", "cree_par")
            .prefetch_related("bons_commande_lies"),
            pk=scan_id,
        )
        membre = request.user.membre
        if not membre.has_perm_app("voir_tous") and (
            not membre.has_perm_app("voir_siens") or scan.cree_par_id != request.user.pk
        ):
            return None
        return scan

    def get(self, request, scan_id: int):
        scan = self._get_scan(request, scan_id)
        if scan is None:
            return _error("Accès refusé.", status.HTTP_403_FORBIDDEN)
        return Response(_scan_payload(scan))

    def patch(self, request, scan_id: int):
        if not request.user.membre.has_perm_app("remplacer"):
            return _error("Permission de remplacement requise.", status.HTTP_403_FORBIDDEN)
        scan = get_object_or_404(DocumentScan, pk=scan_id)
        fichier = request.FILES.get("fichier")
        if not fichier:
            return _error("Choisissez un fichier de remplacement.", status.HTTP_400_BAD_REQUEST)
        try:
            mime_type = valider_fichier(fichier.read(), fichier.name)
            fichier.seek(0)
            drive = get_drive_service()
            folder_id = drive.obtenir_dossier_bc(
                scan.bon_commande.reference, scan.type_document
            )
            new_file_id, new_link = drive.uploader_fichier(
                fichier.read(), fichier.name, mime_type, folder_id
            )
        except FichierInvalideError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except DriveIndisponibleError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        old_file_id = scan.drive_file_id
        scan.drive_file_id = new_file_id
        scan.drive_link = new_link
        scan.nom_fichier = fichier.name
        scan.statut_sync = DocumentScan.STATUT_EN_ATTENTE
        scan.message_erreur = ""
        scan.save(update_fields=[
            "drive_file_id", "drive_link", "nom_fichier", "statut_sync", "message_erreur"
        ])
        cleanup_warning = None
        if old_file_id:
            try:
                drive.supprimer_fichier(old_file_id)
            except DriveIndisponibleError:
                cleanup_warning = (
                    "Le nouveau fichier est actif, mais l’ancien fichier n’a pas pu "
                    "être supprimé de Google Drive."
                )
        if settings.ERP_TYPE == "urium":
            scan.statut_sync = DocumentScan.STATUT_NON_APPLICABLE
            scan.save(update_fields=["statut_sync"])
        else:
            scan = resynchroniser_scan(scan, request.user)
        JournalActivite.objects.create(
            utilisateur=request.user,
            action=JournalActivite.ACTION_REMPLACEMENT,
            bon_commande=scan.bon_commande,
            detail=f"Remplacement du fichier du scan #{scan.pk}.",
        )
        payload = _scan_payload(scan)
        if cleanup_warning:
            payload["avertissement"] = cleanup_warning
        return Response(payload)

    def delete(self, request, scan_id: int):
        if not request.user.membre.has_perm_app("supprimer"):
            return _error("Permission de suppression requise.", status.HTTP_403_FORBIDDEN)
        scan = get_object_or_404(DocumentScan, pk=scan_id)
        scan_data = _scan_payload(scan)
        if scan.drive_file_id:
            try:
                get_drive_service().supprimer_fichier(scan.drive_file_id)
            except DriveIndisponibleError as exc:
                return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        JournalActivite.objects.create(
            utilisateur=request.user,
            action=JournalActivite.ACTION_SUPPRESSION,
            bon_commande=scan.bon_commande,
            detail=f"Suppression du scan {scan.type_document} {scan.numero_document}.",
        )
        scan.delete()
        return Response(scan_data)


class ScanResyncContractView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, scan_id: int):
        if not request.user.membre.has_perm_app("resynchroniser"):
            return _error("Permission de resynchronisation requise.", status.HTTP_403_FORBIDDEN)
        scan = get_object_or_404(
            DocumentScan.objects.select_related("bon_commande", "cree_par")
            .prefetch_related("bons_commande_lies"),
            pk=scan_id,
        )
        if settings.ERP_TYPE == "urium":
            scan.statut_sync = DocumentScan.STATUT_NON_APPLICABLE
            scan.save(update_fields=["statut_sync"])
            JournalActivite.objects.create(
                utilisateur=request.user,
                action=JournalActivite.ACTION_RESYNC,
                bon_commande=scan.bon_commande,
                detail=f"Resynchronisation ignorée pour le scan Urium #{scan.pk} (ERP non applicable).",
            )
        else:
            scan = resynchroniser_scan(scan, request.user)
        return Response(_scan_payload(scan))


class DashboardContractView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _can_view_orders(request.user):
            return _error("Permission requise.", status.HTTP_403_FORBIDDEN)
        today = timezone.localdate()
        scans = DocumentScan.objects.all()
        member = request.user.membre
        if not member.has_perm_app("voir_tous"):
            scans = scans.filter(cree_par=request.user)

        start = today - timedelta(days=6)
        daily_scans = scans.filter(cree_le__date__gte=start, cree_le__date__lte=today)
        counts_by_date = {
            row["day"]: row["count"]
            for row in daily_scans.annotate(day=TruncDate("cree_le"))
            .values("day")
            .annotate(count=Count("pk"))
        }

        order_queryset = BonCommande.objects.all()
        if not member.has_perm_app("voir_tous"):
            visible_order_ids = scans.values_list("bon_commande_id", flat=True)
            linked_order_ids = scans.values_list("bons_commande_lies__id", flat=True)
            order_queryset = order_queryset.filter(
                Q(pk__in=visible_order_ids) | Q(pk__in=linked_order_ids)
            ).distinct()
        incomplete_orders = sum(
            _order_payload(order, user=request.user)["completude"] < 100
            for order in order_queryset
        )
        receipts = BonReception.objects.filter(
            statut=BonReception.STATUT_VALIDE,
            date_reception=today,
        )
        if not member.has_perm_app("voir_tous"):
            receipts = receipts.filter(cree_par=request.user)
        labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
        counts = [
            counts_by_date.get(start + timedelta(days=index), 0)
            for index in range(7)
        ]
        return Response({
            "scansParJour": counts,
            "labelsScans": [
                f"{labels[(start + timedelta(days=index)).weekday()]} "
                f"{(start + timedelta(days=index)).day}"
                for index in range(7)
            ],
            "dossiersIncomplets": incomplete_orders,
            "echecs": scans.filter(statut_sync=DocumentScan.STATUT_ECHEC).count(),
            "brDuJour": receipts.count(),
            "date": today.strftime("%d/%m/%Y"),
            "dateIso": today.isoformat(),
        })


class ActivityJournalContractView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.membre.has_perm_app("voir_audit"):
            return _error("Permission 'voir_audit' requise.", status.HTTP_403_FORBIDDEN)
        queryset = JournalActivite.objects.select_related(
            "utilisateur", "bon_commande"
        )
        period = request.query_params.get("periode", "30")
        try:
            days = int(period)
            if days < 1 or days > 3650:
                raise ValueError
        except ValueError:
            return _error("La période doit être comprise entre 1 et 3650 jours.", status.HTTP_400_BAD_REQUEST)
        queryset = queryset.filter(date__date__gte=timezone.localdate() - timedelta(days=days - 1))
        action = (request.query_params.get("action") or "").strip()
        if action:
            queryset = queryset.filter(action=action)
        search = (request.query_params.get("recherche") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(detail__icontains=search)
                | Q(utilisateur__username__icontains=search)
                | Q(utilisateur__first_name__icontains=search)
                | Q(utilisateur__last_name__icontains=search)
                | Q(bon_commande__reference__icontains=search)
            )
        return Response([
            {
                "id": entry.pk,
                "action": entry.get_action_display(),
                "actionCode": entry.action,
                "utilisateur": (
                    entry.utilisateur.get_full_name() or entry.utilisateur.username
                    if entry.utilisateur else "Utilisateur supprimé"
                ),
                "date": entry.date.isoformat(),
                "detail": entry.detail,
                "bonCommande": entry.bon_commande.reference if entry.bon_commande else None,
                "bonCommandeId": entry.bon_commande_id,
            }
            for entry in queryset.order_by("-date")[:200]
        ])


class ServiceStatusContractView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.membre.has_perm_app("gerer_utilisateurs"):
            return _error("Permission de gestion des services requise.", status.HTTP_403_FORBIDDEN)
        checked_at = timezone.now().isoformat()
        try:
            get_adaptateur().verifier_connexion()
            erp = {"statut": DocumentScan.STATUT_SYNCHRONISE, "detail": "Connexion ERP vérifiée."}
        except (ErpIndisponibleError, ErpErreurError, ValueError) as exc:
            erp = {"statut": DocumentScan.STATUT_ECHEC, "detail": str(exc)}
        try:
            get_drive_service().verifier_connexion()
            drive = {"statut": DocumentScan.STATUT_SYNCHRONISE, "detail": "Accès au dossier Drive vérifié."}
        except DriveIndisponibleError as exc:
            drive = {"statut": DocumentScan.STATUT_ECHEC, "detail": str(exc)}
        return Response({
            "erp": {**erp, "verifieLe": checked_at},
            "drive": {**drive, "verifieLe": checked_at},
        })
