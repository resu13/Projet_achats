from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart

from apps.accounts.models import Membre
from apps.documents.models import BonCommande, DocumentScan, JournalActivite
from apps.reception.models import BonReception, LigneBonCommande, LigneReception
from services.drive_service import DriveIndisponibleError


Utilisateur = get_user_model()


@override_settings(
    ERP_TYPE="urium",
    ENTREPRISE="urium_co",
    NOM_ENTREPRISE="Urium Industries",
    REAUTH_VALIDATION_BR=False,
)
class TestOperationalContractApi(TestCase):
    def setUp(self):
        self.user = Utilisateur.objects.create_user(
            username="ops-admin",
            password="test-password",
            first_name="Camille",
            last_name="Martin",
        )
        self.member = Membre.objects.create(
            utilisateur=self.user,
            entreprise="urium_co",
            role="admin",
            actif=True,
        )
        self.client.force_login(self.user)
        self.order = BonCommande.objects.create(
            reference="BC-OPS-001",
            fournisseur="Fournisseur test",
            statut_erp="confirme",
        )
        self.order_line = LigneBonCommande.objects.create(
            bon_commande=self.order,
            code_article="ART-1",
            designation="Article de test",
            unite="pièce",
            quantite_commandee=Decimal("5"),
        )

    def test_dashboard_and_journal_are_computed_from_database(self):
        DocumentScan.objects.create(
            bon_commande=self.order,
            type_document=DocumentScan.TYPE_BL,
            numero_document="BL-OPS-001",
            nom_fichier="bl.pdf",
            cree_par=self.user,
            statut_sync=DocumentScan.STATUT_ECHEC,
        )
        JournalActivite.objects.create(
            utilisateur=self.user,
            action=JournalActivite.ACTION_SCAN,
            bon_commande=self.order,
            detail="Scan de test",
        )

        dashboard = self.client.get("/api/tableau-de-bord")
        journal = self.client.get("/api/journal")

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["echecs"], 1)
        self.assertEqual(dashboard.json()["dossiersIncomplets"], 1)
        self.assertEqual(len(dashboard.json()["scansParJour"]), 7)
        self.assertEqual(len(dashboard.json()["labelsScans"]), 7)
        self.assertEqual(journal.status_code, 200)
        self.assertEqual(journal.json()[0]["action"], "Scan")
        self.assertEqual(journal.json()[0]["bonCommande"], self.order.reference)

    def test_user_api_creates_accounts_and_returns_one_time_credentials(self):
        response = self.client.post(
            "/api/utilisateurs",
            {"nom": "Sophie Laurent", "identifiant": "sophie.laurent", "role": "magasinier"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["identifiant"], "sophie.laurent")
        password = response.json()["mot_de_passe_temporaire"]
        created = Utilisateur.objects.get(username="sophie.laurent")
        self.assertTrue(created.check_password(password))
        self.assertTrue(created.membre.mot_de_passe_a_changer)
        self.assertEqual(self.client.get("/api/utilisateurs").status_code, 200)

    def test_user_reset_returns_a_new_password_and_last_admin_is_protected(self):
        other_admin = Utilisateur.objects.create_user(
            username="other-admin", password="old-password"
        )
        Membre.objects.create(
            utilisateur=other_admin,
            entreprise="urium_co",
            role="admin",
        )
        reset = self.client.patch(
            f"/api/utilisateurs/{other_admin.pk}",
            {"reset_password": True},
            content_type="application/json",
        )
        self.assertEqual(reset.status_code, 200)
        self.assertTrue(
            other_admin.__class__.objects.get(pk=other_admin.pk).check_password(
                reset.json()["mot_de_passe_temporaire"]
            )
        )

        other_admin.membre.delete()
        blocked = self.client.patch(
            f"/api/utilisateurs/{self.user.pk}",
            {"actif": False},
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 409)

    def test_receipt_draft_validation_cancellation_and_pdf_download(self):
        draft = self.client.post(
            f"/api/bc/{self.order.pk}/br",
            {
                "lignes": [{
                    "ligneId": self.order_line.pk,
                    "article": self.order_line.designation,
                    "quantite": 2,
                }],
                "numeroBl": "BL-F-001",
                "remarques": "Colis complet",
            },
            content_type="application/json",
        )
        self.assertEqual(draft.status_code, 201)
        self.assertEqual(draft.json()["statut"], BonReception.STATUT_BROUILLON)
        self.assertEqual(draft.json()["lignes"][0]["ligneId"], self.order_line.pk)

        invalid_update = self.client.patch(
            f"/api/br/{draft.json()['id']}",
            {"lignes": [{
                "ligneId": self.order_line.pk,
                "article": self.order_line.designation,
                "quantite": 6,
            }]},
            content_type="application/json",
        )
        self.assertEqual(invalid_update.status_code, 400)

        with (
            patch("services.br_service.generer_pdf_br", return_value=b"%PDF test") as generate_pdf,
            patch("services.br_service.get_drive_service") as get_drive,
        ):
            get_drive.return_value.obtenir_dossier_bc.return_value = "folder"
            get_drive.return_value.uploader_fichier.return_value = (
                "drive-file-1",
                "https://drive.example/br.pdf",
            )
            validated = self.client.post(
                f"/api/br/{draft.json()['id']}/valider",
                {"mot_de_passe": ""},
                content_type="application/json",
            )
        self.assertEqual(validated.status_code, 200)
        self.assertEqual(validated.json()["statut"], BonReception.STATUT_VALIDE)
        self.assertTrue(validated.json()["reference"].startswith("BR-"))
        generate_pdf.assert_called_once()

        cancelled = self.client.post(
            f"/api/br/{draft.json()['id']}/annuler",
            {"motif": "Réception enregistrée par erreur"},
            content_type="application/json",
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["statut"], BonReception.STATUT_ANNULE)

        with patch("apps.reception.contract_views.get_drive_service") as get_drive:
            get_drive.return_value.telecharger_fichier.return_value = b"%PDF test"
            pdf = self.client.get(f"/api/br/{draft.json()['id']}/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertEqual(pdf.content, b"%PDF test")

    def test_receipt_validation_rejects_over_receiving_existing_valid_quantities(self):
        valid = BonReception.objects.create(
            bon_commande=self.order,
            numero="BR-2026-0001",
            statut=BonReception.STATUT_VALIDE,
            cree_par=self.user,
        )
        LigneReception.objects.create(
            bon_reception=valid,
            ligne_bon_commande=self.order_line,
            quantite_recue=Decimal("4"),
        )
        draft = BonReception.objects.create(
            bon_commande=self.order,
            cree_par=self.user,
        )
        LigneReception.objects.create(
            bon_reception=draft,
            ligne_bon_commande=self.order_line,
            quantite_recue=Decimal("2"),
        )

        with patch("services.br_service.generer_pdf_br") as generate_pdf:
            response = self.client.post(
                f"/api/br/{draft.pk}/valider",
                {},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reste à recevoir", response.json()["message"])
        generate_pdf.assert_not_called()

    def test_user_management_requires_permission(self):
        self.member.role = "magasinier"
        self.member.save(update_fields=["role"])

        self.assertEqual(self.client.get("/api/utilisateurs").status_code, 403)
        self.assertEqual(self.client.get("/api/journal").status_code, 403)

    def test_urium_stub_does_not_return_fake_orders_and_health_reports_unavailable(self):
        response = self.client.get("/api/bc")
        self.assertEqual(response.status_code, 503)
        self.assertIn("connecteur Urium n’est pas configuré", response.json()["message"])

        with patch("apps.documents.contract_views.get_drive_service") as get_drive:
            get_drive.return_value.verifier_connexion.return_value = None
            health = self.client.get("/api/etat-services")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["erp"]["statut"], DocumentScan.STATUT_ECHEC)
        self.assertEqual(health.json()["drive"]["statut"], DocumentScan.STATUT_SYNCHRONISE)

    def test_password_change_clears_the_forced_change_flag(self):
        self.member.mot_de_passe_a_changer = True
        self.member.save(update_fields=["mot_de_passe_a_changer"])

        response = self.client.post(
            "/api/auth/changer-mot-de-passe/",
            {
                "ancien_mot_de_passe": "test-password",
                "nouveau_mot_de_passe": "A-safe-new-password-938",
                "confirmation": "A-safe-new-password-938",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.member.refresh_from_db()
        self.assertTrue(self.user.check_password("A-safe-new-password-938"))
        self.assertFalse(self.member.mot_de_passe_a_changer)

    def test_document_replacement_resync_and_deletion_use_live_services(self):
        scan = DocumentScan.objects.create(
            bon_commande=self.order,
            type_document=DocumentScan.TYPE_BL,
            numero_document="BL-ACTIONS-001",
            nom_fichier="old.pdf",
            drive_file_id="old-drive-id",
            drive_link="https://drive.example/old",
            cree_par=self.user,
            statut_sync=DocumentScan.STATUT_ECHEC,
        )
        with (
            patch("apps.documents.contract_views.valider_fichier", return_value="application/pdf"),
            patch("apps.documents.contract_views.get_drive_service") as get_drive,
        ):
            get_drive.return_value.obtenir_dossier_bc.return_value = "folder"
            get_drive.return_value.uploader_fichier.return_value = (
                "new-drive-id",
                "https://drive.example/new",
            )
            get_drive.return_value.supprimer_fichier.side_effect = DriveIndisponibleError(
                "Impossible de supprimer le fichier dans Google Drive."
            )
            replaced = self.client.patch(
                f"/api/scans/{scan.pk}",
                data=encode_multipart(
                    BOUNDARY,
                    {"fichier": SimpleUploadedFile("new.pdf", b"%PDF new")},
                ),
                content_type=MULTIPART_CONTENT,
            )
            self.assertEqual(replaced.status_code, 200)
            self.assertEqual(replaced.json()["driveLink"], "https://drive.example/new")
            self.assertIn("ancien fichier", replaced.json()["avertissement"])
            get_drive.return_value.supprimer_fichier.assert_called_once_with("old-drive-id")

        resynced = self.client.post(f"/api/scans/{scan.pk}/resynchroniser")
        self.assertEqual(resynced.status_code, 200)
        self.assertEqual(resynced.json()["statut"], DocumentScan.STATUT_NON_APPLICABLE)

        with patch("apps.documents.contract_views.get_drive_service") as get_drive:
            deleted = self.client.delete(f"/api/scans/{scan.pk}")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(DocumentScan.objects.filter(pk=scan.pk).exists())
        self.assertTrue(
            JournalActivite.objects.filter(
                action=JournalActivite.ACTION_SUPPRESSION,
                detail__contains="BL-ACTIONS-001",
            ).exists()
        )

    def test_document_is_not_deleted_when_drive_deletion_fails(self):
        scan = DocumentScan.objects.create(
            bon_commande=self.order,
            type_document=DocumentScan.TYPE_BL,
            numero_document="BL-DELETE-FAIL",
            nom_fichier="scan.pdf",
            drive_file_id="drive-id",
            cree_par=self.user,
        )
        with patch("apps.documents.contract_views.get_drive_service") as get_drive:
            get_drive.return_value.supprimer_fichier.side_effect = DriveIndisponibleError(
                "Impossible de supprimer le fichier dans Google Drive."
            )
            response = self.client.delete(f"/api/scans/{scan.pk}")

        self.assertEqual(response.status_code, 503)
        self.assertTrue(DocumentScan.objects.filter(pk=scan.pk).exists())
