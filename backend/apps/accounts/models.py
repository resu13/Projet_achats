from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class Utilisateur(AbstractUser):
    """Extension du modèle Django User. Pas de champ supplémentaire ici,
    la configuration enterprise est dans Membre."""
    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"


class Membre(models.Model):
    """Lie un utilisateur à une entreprise (déploiement) avec son rôle."""
    utilisateur = models.OneToOneField(
        Utilisateur, on_delete=models.PROTECT, related_name="membre"
    )
    # L'entreprise est déduite de settings.ENTREPRISE au niveau applicatif,
    # mais on stocke le nom pour l'audit si le .env change.
    entreprise = models.CharField(max_length=100)
    role = models.CharField(max_length=50)
    actif = models.BooleanField(default=True)
    mot_de_passe_a_changer = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Membre"
        verbose_name_plural = "Membres"

    def __str__(self):
        return f"{self.utilisateur.get_full_name()} ({self.role}) — {self.entreprise}"

    @property
    def permissions(self):
        from services.roles import get_role_definition
        return get_role_definition(settings.ERP_TYPE, self.role)["permissions"]

    def has_perm_app(self, permission: str) -> bool:
        from services.roles import has_permission
        return self.actif and has_permission(settings.ERP_TYPE, self.role, permission)

    def peut_scanner_type(self, type_document: str) -> bool:
        from services.roles import can_scan_type
        return self.actif and can_scan_type(settings.ERP_TYPE, self.role, type_document)
