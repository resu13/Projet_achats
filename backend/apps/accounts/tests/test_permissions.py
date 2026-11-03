import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from apps.accounts.models import Membre
from apps.accounts.permissions import PermissionApp, _check_membre_permission
from rest_framework.exceptions import PermissionDenied
from services.roles import has_permission, can_scan_type, ROLES

Utilisateur = get_user_model()


class TestMatricePermissionsOdoo(TestCase):
    """Teste chaque rôle Odoo contre chaque permission."""

    def setUp(self):
        self.user = Utilisateur.objects.create_user(username="test", password="testpass123!")

    def _make_membre(self, role, actif=True):
        try:
            self.user.membre.delete()
        except Membre.DoesNotExist:
            pass
        return Membre.objects.create(
            utilisateur=self.user,
            entreprise="odoo_co",
            role=role,
            actif=actif,
        )

    @patch("apps.accounts.models.settings")
    def test_operateur_permissions(self, mock_settings):
        mock_settings.ERP_TYPE = "odoo"
        membre = self._make_membre("operateur")
        with patch("apps.accounts.models.settings", mock_settings):
            assert membre.has_perm_app("scanner") is True
            assert membre.has_perm_app("voir_siens") is True
            assert membre.has_perm_app("voir_tous") is False
            assert membre.has_perm_app("remplacer") is False
            assert membre.has_perm_app("supprimer") is False
            assert membre.has_perm_app("generer_br") is False
            assert membre.peut_scanner_type("BL") is True
            assert membre.peut_scanner_type("FACTURE") is False

    @patch("apps.accounts.models.settings")
    def test_comptable_permissions(self, mock_settings):
        mock_settings.ERP_TYPE = "odoo"
        membre = self._make_membre("comptable")
        with patch("apps.accounts.models.settings", mock_settings):
            assert membre.has_perm_app("scanner") is True
            assert membre.has_perm_app("voir_tous") is True
            assert membre.has_perm_app("resynchroniser") is True
            assert membre.has_perm_app("remplacer") is False
            assert membre.peut_scanner_type("BL") is True
            assert membre.peut_scanner_type("FACTURE") is True

    @patch("apps.accounts.models.settings")
    def test_lecteur_permissions(self, mock_settings):
        mock_settings.ERP_TYPE = "odoo"
        membre = self._make_membre("lecteur")
        with patch("apps.accounts.models.settings", mock_settings):
            assert membre.has_perm_app("scanner") is False
            assert membre.has_perm_app("voir_tous") is True
            assert membre.has_perm_app("voir_audit") is True
            assert membre.has_perm_app("remplacer") is False
            assert membre.peut_scanner_type("BL") is False

    @patch("apps.accounts.models.settings")
    def test_admin_odoo_toutes_permissions(self, mock_settings):
        mock_settings.ERP_TYPE = "odoo"
        membre = self._make_membre("admin")
        with patch("apps.accounts.models.settings", mock_settings):
            for perm in ["scanner", "voir_siens", "voir_tous", "remplacer",
                         "supprimer", "resynchroniser", "voir_audit", "gerer_utilisateurs"]:
                assert membre.has_perm_app(perm) is True, f"Admin odoo devrait avoir '{perm}'"
            # Pas de permissions Urium
            assert membre.has_perm_app("generer_br") is False
            assert membre.has_perm_app("annuler_br") is False

    @patch("apps.accounts.models.settings")
    def test_compte_desactive_bloque(self, mock_settings):
        mock_settings.ERP_TYPE = "odoo"
        membre = self._make_membre("admin", actif=False)
        with patch("apps.accounts.models.settings", mock_settings):
            assert membre.has_perm_app("scanner") is False


class TestMatricePermissionsUrium(TestCase):
    def setUp(self):
        self.user = Utilisateur.objects.create_user(username="utest", password="testpass123!")

    def _make_membre(self, role, actif=True):
        try:
            self.user.membre.delete()
        except Membre.DoesNotExist:
            pass
        return Membre.objects.create(
            utilisateur=self.user,
            entreprise="urium_co",
            role=role,
            actif=actif,
        )

    @patch("apps.accounts.models.settings")
    def test_magasinier_urium(self, mock_settings):
        mock_settings.ERP_TYPE = "urium"
        membre = self._make_membre("magasinier")
        with patch("apps.accounts.models.settings", mock_settings):
            assert membre.has_perm_app("scanner") is True
            assert membre.has_perm_app("generer_br") is True
            assert membre.has_perm_app("annuler_br") is False
            assert membre.has_perm_app("voir_tous") is False
            assert membre.peut_scanner_type("BL") is True
            assert membre.peut_scanner_type("FACTURE") is False

    @patch("apps.accounts.models.settings")
    def test_directeur_urium(self, mock_settings):
        mock_settings.ERP_TYPE = "urium"
        membre = self._make_membre("directeur")
        with patch("apps.accounts.models.settings", mock_settings):
            for perm in ["scanner", "voir_siens", "voir_tous", "remplacer",
                         "supprimer", "resynchroniser", "voir_audit", "generer_br", "annuler_br"]:
                assert membre.has_perm_app(perm) is True, f"Directeur urium devrait avoir '{perm}'"

    @patch("apps.accounts.models.settings")
    def test_admin_urium_toutes_permissions(self, mock_settings):
        mock_settings.ERP_TYPE = "urium"
        membre = self._make_membre("admin")
        with patch("apps.accounts.models.settings", mock_settings):
            for perm in ["scanner", "voir_siens", "voir_tous", "remplacer", "supprimer",
                         "resynchroniser", "voir_audit", "gerer_utilisateurs", "generer_br", "annuler_br"]:
                assert membre.has_perm_app(perm) is True, f"Admin urium devrait avoir '{perm}'"


class TestCheckPermissionServeur(TestCase):
    """Vérifie que _check_membre_permission lève PermissionDenied dans tous les cas limites."""

    def setUp(self):
        self.user = Utilisateur.objects.create_user(username="chktest", password="testpass123!")
        self.membre = Membre.objects.create(
            utilisateur=self.user, entreprise="odoo_co", role="operateur", actif=True
        )

    @patch("apps.accounts.permissions.settings")
    def test_permission_ok(self, mock_settings):
        mock_settings.ERP_TYPE = "odoo"
        _check_membre_permission(self.user, "scanner")  # Ne doit pas lever

    @patch("apps.accounts.permissions.settings")
    def test_permission_refusee(self, mock_settings):
        mock_settings.ERP_TYPE = "odoo"
        with pytest.raises(PermissionDenied):
            _check_membre_permission(self.user, "supprimer")

    def test_utilisateur_non_authentifie(self):
        mock_user = MagicMock()
        mock_user.is_authenticated = False
        with pytest.raises(PermissionDenied):
            _check_membre_permission(mock_user, "scanner")


class TestRolesService(TestCase):
    """Teste le fichier centralisé roles.py."""

    def test_roles_odoo_valides(self):
        for role in ["operateur", "comptable", "responsable", "lecteur", "admin"]:
            assert has_permission("odoo", role, "voir_siens") is not None

    def test_roles_urium_valides(self):
        for role in ["magasinier", "achats", "directeur", "admin"]:
            assert has_permission("urium", role, "voir_siens") is not None

    def test_role_inconnu_leve_erreur(self):
        from services.roles import get_role_definition
        with pytest.raises(ValueError):
            get_role_definition("odoo", "role_inexistant")

    def test_erp_inconnu_leve_erreur(self):
        from services.roles import get_role_definition
        with pytest.raises(ValueError):
            get_role_definition("sap", "admin")

    def test_restriction_type_scan(self):
        # Opérateur Odoo : BL seulement
        assert can_scan_type("odoo", "operateur", "BL") is True
        assert can_scan_type("odoo", "operateur", "FACTURE") is False
        # Magasinier Urium : BL seulement
        assert can_scan_type("urium", "magasinier", "BL") is True
        assert can_scan_type("urium", "magasinier", "FACTURE") is False
        # BR jamais scannable (aucun rôle)
        for erp, role in [("odoo", "admin"), ("urium", "admin")]:
            assert can_scan_type(erp, role, "BR") is False

    def test_generer_br_uniquement_urium(self):
        # Aucun rôle Odoo ne peut generer_br
        for role in ROLES["odoo"]:
            assert has_permission("odoo", role, "generer_br") is False
        # Tous les rôles Urium (sauf si vide) peuvent generer_br
        for role in ["magasinier", "achats", "directeur", "admin"]:
            assert has_permission("urium", role, "generer_br") is True
