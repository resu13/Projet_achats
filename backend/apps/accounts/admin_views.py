import re
import secrets
import unicodedata

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membre, Utilisateur
from apps.documents.models import JournalActivite
from services.roles import ROLES


def _user_payload(membre):
    user = membre.utilisateur
    return {
        "id": user.pk,
        "nom": user.get_full_name() or user.username,
        "identifiant": user.username,
        "role": membre.role,
        "entreprise": settings.NOM_ENTREPRISE,
        "actif": membre.actif,
    }


def _temporary_password():
    return secrets.token_urlsafe(24)


def _default_username(name):
    normalized = unicodedata.normalize("NFKD", name)
    slug = re.sub(r"[^a-zA-Z0-9._-]+", ".", normalized.encode("ascii", "ignore").decode()).strip(".-_")
    return slug[:120] or "utilisateur"


def _journal_user_change(user, action):
    JournalActivite.objects.create(
        utilisateur=user,
        action=JournalActivite.ACTION_GESTION_USER,
        detail=action,
    )


class UserAdminListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def _authorize(self, request):
        if not request.user.membre.has_perm_app("gerer_utilisateurs"):
            return Response(
                {"message": "Permission de gestion des utilisateurs requise."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def get(self, request):
        denied = self._authorize(request)
        if denied:
            return denied
        company = settings.ENTREPRISE
        members = Membre.objects.select_related("utilisateur").filter(
            entreprise=company
        ).order_by("utilisateur__last_name", "utilisateur__first_name", "utilisateur__username")
        return Response({
            "utilisateurs": [_user_payload(member) for member in members],
            "rolesDisponibles": list(ROLES.get(settings.ERP_TYPE.lower(), {}).keys()),
        })

    def post(self, request):
        denied = self._authorize(request)
        if denied:
            return denied
        if not isinstance(request.data, dict):
            return Response({"message": "Le corps de la requête doit être un objet."}, status=status.HTTP_400_BAD_REQUEST)

        name = str(request.data.get("nom") or "").strip()
        username = str(request.data.get("identifiant") or _default_username(name)).strip()
        role = str(request.data.get("role") or "").strip()
        allowed_roles = ROLES.get(settings.ERP_TYPE.lower(), {})
        if not name or not username or not role:
            return Response(
                {"message": "Le nom, l’identifiant et le rôle sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if role not in allowed_roles:
            return Response({"message": "Ce rôle ne correspond pas à l’entreprise."}, status=status.HTTP_400_BAD_REQUEST)
        if len(username) > 150 or not re.fullmatch(r"[\w.@+-]+", username, flags=re.UNICODE):
            return Response({"message": "L’identifiant contient des caractères non autorisés."}, status=status.HTTP_400_BAD_REQUEST)
        if Utilisateur.objects.filter(username__iexact=username).exists():
            return Response({"message": "Cet identifiant est déjà utilisé."}, status=status.HTTP_409_CONFLICT)

        name_parts = name.split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:])
        password = _temporary_password()
        user = Utilisateur(
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )
        user.set_password(password)
        with transaction.atomic():
            user.save()
            member = Membre.objects.create(
                utilisateur=user,
                entreprise=settings.ENTREPRISE,
                role=role,
                actif=True,
                mot_de_passe_a_changer=True,
            )
            _journal_user_change(request.user, f"Création du compte {username} avec le rôle {role}.")
        return Response({
            **_user_payload(member),
            "mot_de_passe_temporaire": password,
        }, status=status.HTTP_201_CREATED)


class UserAdminDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, user_id):
        actor_member = request.user.membre
        if not actor_member.has_perm_app("gerer_utilisateurs"):
            return Response(
                {"message": "Permission de gestion des utilisateurs requise."},
                status=status.HTTP_403_FORBIDDEN,
            )
        changes = request.data
        if not isinstance(changes, dict):
            return Response({"message": "Le corps de la requête doit être un objet."}, status=status.HTTP_400_BAD_REQUEST)
        allowed_fields = {"role", "actif", "reset_password"}
        if set(changes) - allowed_fields:
            return Response({"message": "Certains champs ne peuvent pas être modifiés."}, status=status.HTTP_400_BAD_REQUEST)

        new_role = changes.get("role")
        active = changes.get("actif")
        reset_password = changes.get("reset_password", False)
        roles = ROLES.get(settings.ERP_TYPE.lower(), {})
        if new_role is not None and (
            not isinstance(new_role, str) or new_role not in roles
        ):
            return Response({"message": "Ce rôle ne correspond pas à l’entreprise."}, status=status.HTTP_400_BAD_REQUEST)
        if active is not None and not isinstance(active, bool):
            return Response({"message": "Le statut actif doit être un booléen."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(reset_password, bool):
            return Response({"message": "reset_password doit être un booléen."}, status=status.HTTP_400_BAD_REQUEST)

        temporary_password = None
        with transaction.atomic():
            active_admins = list(
                Membre.objects.select_for_update()
                .filter(entreprise=settings.ENTREPRISE, role="admin", actif=True)
                .order_by("pk")
            )
            member = Membre.objects.select_for_update().select_related("utilisateur").filter(
                utilisateur_id=user_id,
                entreprise=settings.ENTREPRISE,
            ).first()
            if member is None:
                return Response({"message": "Utilisateur introuvable."}, status=status.HTTP_404_NOT_FOUND)

            removing_admin = member.role == "admin" and member.actif and (
                (new_role is not None and new_role != "admin") or active is False
            )
            if removing_admin and len(active_admins) <= 1:
                return Response({"message": "Le dernier administrateur actif ne peut pas être rétrogradé ou désactivé."}, status=status.HTTP_409_CONFLICT)
            if active is False and member.utilisateur_id == request.user.pk:
                return Response({"message": "Vous ne pouvez pas désactiver votre propre compte."}, status=status.HTTP_400_BAD_REQUEST)

            details = []
            if new_role is not None and new_role != member.role:
                details.append(f"rôle {member.role} → {new_role}")
                member.role = new_role
            if active is not None and active != member.actif:
                details.append("compte activé" if active else "compte désactivé")
                member.actif = active
            member.save(update_fields=["role", "actif"])
            if reset_password:
                temporary_password = _temporary_password()
                member.utilisateur.set_password(temporary_password)
                member.utilisateur.save(update_fields=["password"])
                member.mot_de_passe_a_changer = True
                member.save(update_fields=["mot_de_passe_a_changer"])
                details.append("mot de passe réinitialisé")
            if details:
                _journal_user_change(
                    request.user,
                    f"Mise à jour du compte {member.utilisateur.username} : {', '.join(details)}.",
                )

        return Response({
            **_user_payload(member),
            **({"mot_de_passe_temporaire": temporary_password} if temporary_password else {}),
        })
