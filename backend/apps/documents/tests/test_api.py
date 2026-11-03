from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from apps.documents.models import BonCommande, DocumentScan
from apps.accounts.models import Membre

Utilisateur = get_user_model()


class TestDocumentsApi(TestCase):
    def setUp(self):
        self.user = Utilisateur.objects.create_user(username="docapi", password="Password123!")
        Membre.objects.create(utilisateur=self.user, entreprise="odoo_co", role="operateur", actif=True)
        self.bc = BonCommande.objects.create(
            reference="BC-2024-001",
            fournisseur="Fournisseur Test",
            statut_erp="confirmé",
        )

    @patch("apps.documents.views.get_adaptateur")
    def test_search_bon_commande_endpoint(self, mock_get_adaptateur):
        mock_get_adaptateur.return_value.rechercher_bc.return_value = [{
            "reference": "BC-2024-001",
            "fournisseur": "Fournisseur Test",
            "date": "2024-01-15",
            "statut_erp": "confirmé",
            "erp_id": "1001",
        }]

        self.client.force_login(self.user)
        response = self.client.get("/api/documents/bons-commande/", {"reference": "BC-2024-001"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["reference"], "BC-2024-001")

    @patch("apps.documents.views.traiter_scan")
    def test_create_scan_endpoint(self, mock_traiter_scan):
        mock_traiter_scan.return_value = DocumentScan.objects.create(
            bon_commande=self.bc,
            type_document="BL",
            numero_document="DOC-001",
            nom_fichier="scan.pdf",
            drive_file_id="drive_123",
            drive_link="https://drive.google.com/file/d/drive_123/view",
            statut_sync=DocumentScan.STATUT_SYNCHRONISE,
            cree_par=self.user,
        )

        self.client.force_login(self.user)
        response = self.client.post(
            "/api/documents/scans/ajouter/",
            {
                "reference_bc": self.bc.reference,
                "type_document": "BL",
                "numero_document": "DOC-001",
                "fichier": SimpleUploadedFile("scan.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["numero_document"], "DOC-001")
