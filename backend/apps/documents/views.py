from __future__ import annotations

from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import BonCommande, DocumentScan, JournalActivite
from apps.documents.serializers import BonCommandeSerializer, DocumentScanSerializer
from apps.erp_adapters import get_adaptateur
from apps.reception.models import BonReception
from services.scan_pipeline import traiter_scan


class BonCommandeSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membre = request.user.membre
        if not membre.has_perm_app("voir_siens") and not membre.has_perm_app("voir_tous"):
            return Response({"detail": "Permission requise."}, status=status.HTTP_403_FORBIDDEN)

        criteres = {
            "reference": request.GET.get("reference") or None,
            "fournisseur": request.GET.get("fournisseur") or None,
            "date_debut": request.GET.get("date_debut") or None,
            "date_fin": request.GET.get("date_fin") or None,
        }
        try:
            bcs = get_adaptateur().rechercher_bc(criteres)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - dépendance ERP externe
            return Response({"detail": f"Impossible de consulter l'ERP : {exc}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(bcs)


class BonCommandeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, reference):
        membre = request.user.membre
        if not membre.has_perm_app("voir_siens") and not membre.has_perm_app("voir_tous"):
            return Response({"detail": "Permission requise."}, status=status.HTTP_403_FORBIDDEN)

        try:
            bc_erp = get_adaptateur().lire_bc(reference)
        except Exception as exc:  # pragma: no cover - dépendance ERP externe
            return Response({"detail": f"Impossible de lire le BC : {exc}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if bc_erp is None:
            raise Http404("Bon de commande introuvable.")

        local_bc, _ = BonCommande.objects.update_or_create(
            reference=reference,
            defaults={
                "fournisseur": bc_erp.get("fournisseur", ""),
                "date": bc_erp.get("date"),
                "statut_erp": bc_erp.get("statut_erp", ""),
                "montant": bc_erp.get("montant"),
                "devise": bc_erp.get("devise", ""),
                "erp_id": bc_erp.get("erp_id", ""),
                "derniere_synchro": None,
            },
        )

        scans = DocumentScan.objects.filter(
            Q(bon_commande=local_bc) | Q(bons_commande_lies=local_bc)
        ).distinct().order_by("-cree_le")
        bres = []
        if getattr(__import__("django.conf", fromlist=["settings"]).conf.settings, "ERP_TYPE", "") == "urium":
            bres = list(BonReception.objects.filter(bon_commande=local_bc).order_by("-cree_le").values(
                "id",
                "numero",
                "date_reception",
                "statut",
                "numero_bl_fournisseur",
                "valide_le",
            ))

        data = {
            "bon_commande": BonCommandeSerializer(local_bc).data,
            "erp": bc_erp,
            "scans": DocumentScanSerializer(scans, many=True).data,
            "bons_reception": bres,
        }
        return Response(data)


class ScanListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membre = request.user.membre
        queryset = DocumentScan.objects.select_related("bon_commande", "cree_par")
        if not membre.has_perm_app("voir_tous"):
            queryset = queryset.filter(cree_par=request.user)

        type_document = request.GET.get("type_document")
        if type_document:
            queryset = queryset.filter(type_document=type_document)

        reference = request.GET.get("reference")
        if reference:
            queryset = queryset.filter(
                Q(bon_commande__reference__icontains=reference)
                | Q(bons_commande_lies__reference__icontains=reference)
            ).distinct()

        statut = request.GET.get("statut_sync")
        if statut:
            queryset = queryset.filter(statut_sync=statut)

        return Response(DocumentScanSerializer(queryset.order_by("-cree_le")[:200], many=True).data)


class ScanCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        membre = request.user.membre
        if not membre.has_perm_app("scanner"):
            return Response({"detail": "Permission de scan requise."}, status=status.HTTP_403_FORBIDDEN)

        reference_bc = (request.data.get("reference_bc") or "").strip()
        type_document = (request.data.get("type_document") or "").strip().upper()
        numero_document = (request.data.get("numero_document") or "").strip()
        fichier = request.FILES.get("fichier")

        if not reference_bc or not type_document or not numero_document or not fichier:
            return Response({"detail": "reference_bc, type_document, numero_document et fichier sont obligatoires."}, status=status.HTTP_400_BAD_REQUEST)

        if type_document not in ["BL", "FACTURE"]:
            return Response({"detail": "Type de document invalide."}, status=status.HTTP_400_BAD_REQUEST)

        if not membre.peut_scanner_type(type_document):
            return Response({"detail": f"Vous n'êtes pas autorisé à scanner le type '{type_document}'."}, status=status.HTTP_403_FORBIDDEN)

        bon_commande, _ = BonCommande.objects.get_or_create(
            reference=reference_bc,
            defaults={
                "fournisseur": "À synchroniser",
                "statut_erp": "inconnu",
            },
        )

        try:
            scan = traiter_scan(
                utilisateur=request.user,
                bon_commande=bon_commande,
                type_document=type_document,
                numero_document=numero_document,
                nom_fichier=fichier.name,
                contenu=fichier.read(),
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        JournalActivite.objects.create(
            utilisateur=request.user,
            action=JournalActivite.ACTION_SCAN,
            bon_commande=bon_commande,
            detail=f"Création/traitement du scan {type_document} {numero_document}",
        )

        return Response(DocumentScanSerializer(scan).data, status=status.HTTP_201_CREATED)
