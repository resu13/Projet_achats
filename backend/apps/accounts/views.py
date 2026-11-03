from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from .models import Membre
from .serializers import ChangerMotDePasseSerializer, serialiser_me
from apps.documents.models import JournalActivite


class LoginView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        """Retourne le token CSRF."""
        return Response({"csrfToken": get_token(request)})

    def post(self, request):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")
        if not username or not password:
            return Response(
                {"detail": "Identifiant et mot de passe obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Identifiant ou mot de passe incorrect."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            membre = user.membre
        except Membre.DoesNotExist:
            return Response(
                {"detail": "Profil utilisateur introuvable."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not membre.actif:
            return Response(
                {"detail": "Votre compte est désactivé. Contactez l'administrateur."},
                status=status.HTTP_403_FORBIDDEN,
            )
        login(request, user)
        get_token(request)
        JournalActivite.objects.create(
            utilisateur=user,
            action="connexion",
            detail=f"Connexion depuis {_get_ip(request)}",
        )
        return Response(serialiser_me(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"detail": "Déconnexion réussie."})


class MeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"message": "Votre session a expiré. Veuillez vous reconnecter."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            return Response(serialiser_me(request.user))
        except Membre.DoesNotExist:
            return Response(
                {"message": "Profil utilisateur introuvable."},
                status=status.HTTP_403_FORBIDDEN,
            )


class ChangerMotDePasseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangerMotDePasseSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            update_session_auth_hash(request, request.user)
            return Response({"detail": "Mot de passe modifié avec succès."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def axes_lockout_response(request, credentials, *args, **kwargs):
    """Réponse JSON personnalisée lors du verrouillage du compte par django-axes."""
    from rest_framework.response import Response
    from rest_framework import status
    return Response(
        {"detail": "Trop de tentatives échouées. Compte temporairement verrouillé."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _get_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
