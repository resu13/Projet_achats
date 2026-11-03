from rest_framework import serializers

from apps.documents.models import BonCommande, DocumentScan


class BonCommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BonCommande
        fields = [
            "id",
            "reference",
            "fournisseur",
            "date",
            "statut_erp",
            "montant",
            "devise",
            "derniere_synchro",
            "erp_id",
        ]


class DocumentScanSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentScan
        fields = [
            "id",
            "bon_commande",
            "type_document",
            "numero_document",
            "nom_fichier",
            "drive_file_id",
            "drive_link",
            "statut_sync",
            "message_erreur",
            "cree_par",
            "cree_le",
            "remplace_par",
        ]
