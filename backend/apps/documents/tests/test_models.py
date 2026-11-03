from django.test import TestCase
from apps.documents.models import BonCommande, DocumentScan
from django.contrib.auth import get_user_model
from apps.accounts.models import Membre
from django.db import IntegrityError

Utilisateur = get_user_model()


class TestDocumentScanDoublon(TestCase):
    def setUp(self):
        self.user = Utilisateur.objects.create_user(username="scantest", password="testpass123!")
        Membre.objects.create(utilisateur=self.user, entreprise="odoo_co", role="operateur", actif=True)
        self.bc = BonCommande.objects.create(reference="BC-2024-001", fournisseur="Fournisseur Test")

    def test_doublon_bloque(self):
        DocumentScan.objects.create(
            bon_commande=self.bc,
            type_document="BL",
            numero_document="BL-0001",
            nom_fichier="bl.pdf",
            cree_par=self.user,
        )
        with self.assertRaises(IntegrityError):
            DocumentScan.objects.create(
                bon_commande=self.bc,
                type_document="BL",
                numero_document="BL-0001",
                nom_fichier="bl2.pdf",
                cree_par=self.user,
            )

    def test_meme_numero_type_different_autorise(self):
        DocumentScan.objects.create(
            bon_commande=self.bc,
            type_document="BL",
            numero_document="DOC-0001",
            nom_fichier="bl.pdf",
            cree_par=self.user,
        )
        # Même numéro mais type différent → autorisé
        DocumentScan.objects.create(
            bon_commande=self.bc,
            type_document="FACTURE",
            numero_document="DOC-0001",
            nom_fichier="fact.pdf",
            cree_par=self.user,
        )
        assert DocumentScan.objects.filter(bon_commande=self.bc).count() == 2
