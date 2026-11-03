from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.accounts.models import Membre
from apps.documents.models import BonCommande, DocumentScan


Utilisateur = get_user_model()


@override_settings(
    ERP_TYPE="odoo",
    ENTREPRISE="odoo_co",
    NOM_ENTREPRISE="Odoo Construction",
    REAUTH_VALIDATION_BR=False,
)
class TestFrontendApiContract(TestCase):
    def setUp(self):
        self.user = Utilisateur.objects.create_user(
            username="contract-user",
            password="test-password",
            first_name="Sophie",
            last_name="Laurent",
        )
        Membre.objects.create(
            utilisateur=self.user,
            entreprise="odoo_co",
            role="responsable",
            actif=True,
        )
        self.client.force_login(self.user)

    def test_me_returns_the_frontend_contract(self):
        response = self.client.get("/api/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["utilisateur"], {
            "nom": "Sophie Laurent",
            "role": "responsable",
        })
        self.assertEqual(response.json()["entreprise"]["code"], "odoo_co")
        self.assertIn("voir_tous", response.json()["permissions"])
        self.assertEqual(response.json()["types_scannables"], ["BL", "FACTURE"])

    def test_unauthenticated_me_returns_401(self):
        self.client.logout()

        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_session_login_uses_the_shared_me_contract(self):
        self.client.logout()
        csrf_response = self.client.get("/api/auth/login")
        csrf = csrf_response.json()["csrfToken"]
        csrf_cookie_before_login = csrf_response.cookies["csrftoken"].value

        response = self.client.post(
            "/api/auth/login",
            {"username": "contract-user", "password": "test-password"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["utilisateur"]["nom"], "Sophie Laurent")
        self.assertIn("csrftoken", response.cookies)
        self.assertNotEqual(response.cookies["csrftoken"].value, csrf_cookie_before_login)

    @patch("apps.documents.contract_views.get_adaptateur")
    def test_purchase_order_search_returns_frontend_shape(self, get_adapter):
        get_adapter.return_value.rechercher_bc.return_value = [{
            "reference": "BC-2026-001",
            "fournisseur": "Fournisseur Test",
            "date": "2026-10-28",
            "statut_erp": "purchase",
            "erp_id": "1001",
            "montant": 1250,
            "devise": "MAD",
        }]

        response = self.client.get("/api/bc", {"recherche": "BC-2026"})

        self.assertEqual(response.status_code, 200)
        order = response.json()[0]
        self.assertEqual(order["reference"], "BC-2026-001")
        self.assertIsInstance(order["id"], int)
        self.assertEqual(order["statutErp"], "purchase")
        self.assertEqual(order["lignes"], [])

    @patch("apps.documents.contract_views.get_adaptateur")
    def test_purchase_order_detail_returns_lines_and_local_identifier(self, get_adapter):
        order = BonCommande.objects.create(
            reference="BC-DETAIL-1",
            fournisseur="Fournisseur Test",
        )
        get_adapter.return_value.lire_bc.return_value = {
            "reference": order.reference,
            "fournisseur": order.fournisseur,
            "date": "2026-10-28",
            "statut_erp": "purchase",
            "erp_id": "1001",
            "montant": 1250,
            "devise": "MAD",
            "lignes": [{
                "code_article": "A-1",
                "designation": "Article test",
                "unite": "pièce",
                "quantite_commandee": 3,
            }],
        }

        response = self.client.get(f"/api/bc/{order.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], order.pk)
        self.assertEqual(response.json()["lignes"][0]["article"], "Article test")
        self.assertEqual(response.json()["lignes"][0]["commande"], 3)
        self.assertEqual(response.json()["documents"], [])
        self.assertEqual(response.json()["receptions"], [])
        first_line_id = order.lignes.get().pk

        updated_response = self.client.get(f"/api/bc/{order.pk}")

        self.assertEqual(updated_response.status_code, 200)
        self.assertEqual(order.lignes.filter(actif=True).count(), 1)
        self.assertEqual(order.lignes.get(actif=True).pk, first_line_id)

    @patch("apps.documents.contract_views.traiter_scan")
    def test_scan_creation_keeps_all_selected_orders(self, process_scan):
        orders = [
            BonCommande.objects.create(reference="BC-001", fournisseur="Alpha"),
            BonCommande.objects.create(reference="BC-002", fournisseur="Beta"),
        ]

        def create_scan(**kwargs):
            scan = DocumentScan.objects.create(
                bon_commande=kwargs["bon_commande"],
                type_document=kwargs["type_document"],
                numero_document=kwargs["numero_document"],
                nom_fichier=kwargs["nom_fichier"],
                cree_par=kwargs["utilisateur"],
            )
            scan.bons_commande_lies.set(kwargs["bons_commande"])
            return scan

        process_scan.side_effect = create_scan
        response = self.client.post(
            "/api/scans",
            {
                "ids_bc": f"[{orders[0].pk},{orders[1].pk}]",
                "type": "BL",
                "numero_document": "BL-001",
                "fichier": SimpleUploadedFile(
                    "scan.pdf", b"%PDF-1.4 test", content_type="application/pdf"
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["bc"], ["BC-001", "BC-002"])
        self.assertEqual(response.json()["bcIds"], [orders[0].pk, orders[1].pk])
        process_scan.assert_called_once()

        listing = self.client.get("/api/scans")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()[0]["bc"], ["BC-001", "BC-002"])
