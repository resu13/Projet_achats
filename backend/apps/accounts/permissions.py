from functools import wraps
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from django.conf import settings


def require_permission(permission):
    """Décorateur de vue DRF : vérifie une permission applicative."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(self, request, *args, **kwargs):
            _check_membre_permission(request.user, permission)
            return view_func(self, request, *args, **kwargs)
        return _wrapped_view
    return decorator


def _check_membre_permission(user, permission):
    if not user.is_authenticated:
        raise PermissionDenied("Authentification requise.")
    try:
        membre = user.membre
    except Exception:
        raise PermissionDenied("Profil utilisateur introuvable.")
    if not membre.actif:
        raise PermissionDenied("Votre compte est désactivé.")
    if not membre.has_perm_app(permission):
        raise PermissionDenied(f"Permission '{permission}' requise.")


class PermissionApp(BasePermission):
    """Classe de permission DRF générique. Usage : PermissionApp.for_perm('scanner')"""
    permission_required = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        try:
            membre = request.user.membre
        except Exception:
            return False
        return membre.actif and membre.has_perm_app(self.permission_required)

    @classmethod
    def for_perm(cls, perm):
        return type(f"Has{perm.title()}Permission", (cls,), {"permission_required": perm})


# Permissions préconstruites
CanScanner = PermissionApp.for_perm("scanner")
CanVoirTous = PermissionApp.for_perm("voir_tous")
CanRemplacer = PermissionApp.for_perm("remplacer")
CanSupprimer = PermissionApp.for_perm("supprimer")
CanResynchroniser = PermissionApp.for_perm("resynchroniser")
CanVoirAudit = PermissionApp.for_perm("voir_audit")
CanGererUtilisateurs = PermissionApp.for_perm("gerer_utilisateurs")
CanGenererBr = PermissionApp.for_perm("generer_br")
CanAnnulerBr = PermissionApp.for_perm("annuler_br")
