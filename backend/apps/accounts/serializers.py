from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import Utilisateur, Membre
from django.conf import settings
from services.roles import ROLES


class MembreSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    types_scan_autorises = serializers.SerializerMethodField()

    class Meta:
        model = Membre
        fields = ["entreprise", "role", "actif", "permissions", "types_scan_autorises"]

    def get_permissions(self, obj):
        try:
            return list(ROLES[settings.ERP_TYPE][obj.role]["permissions"])
        except KeyError:
            return []

    def get_types_scan_autorises(self, obj):
        try:
            return ROLES[settings.ERP_TYPE][obj.role]["types_scan_autorises"]
        except KeyError:
            return []


class UtilisateurSerializer(serializers.ModelSerializer):
    membre = MembreSerializer(read_only=True)
    nom_complet = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = ["id", "username", "first_name", "last_name", "email", "nom_complet", "membre"]

    def get_nom_complet(self, obj):
        return obj.get_full_name() or obj.username


def serialiser_me(user):
    membre = user.membre
    entreprise = settings.ENTREPRISE
    nom_entreprise = settings.NOM_ENTREPRISE
    erp_type = settings.ERP_TYPE.lower()
    return {
        "utilisateur": {
            "nom": user.get_full_name() or user.username,
            "role": membre.role,
        },
        "entreprise": {
            "code": entreprise,
            "nom": nom_entreprise,
            "logo": "".join(part[0] for part in nom_entreprise.split()[:2]).upper(),
            "couleur": "#6d4aff" if erp_type == "urium" else "#0e7490",
            "erp_type": erp_type,
        },
        "permissions": sorted(membre.permissions),
        "types_scannables": list(ROLES[erp_type][membre.role]["types_scan_autorises"]),
        "options": {
            "reauth_validation_br": settings.REAUTH_VALIDATION_BR,
            "mot_de_passe_a_changer": membre.mot_de_passe_a_changer,
        },
    }


class ChangerMotDePasseSerializer(serializers.Serializer):
    ancien_mot_de_passe = serializers.CharField(write_only=True)
    nouveau_mot_de_passe = serializers.CharField(write_only=True)
    confirmation = serializers.CharField(write_only=True)

    def validate_ancien_mot_de_passe(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate(self, data):
        if data["nouveau_mot_de_passe"] != data["confirmation"]:
            raise serializers.ValidationError(
                {"confirmation": "Les mots de passe ne correspondent pas."}
            )
        validate_password(data["nouveau_mot_de_passe"], self.context["request"].user)
        return data

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["nouveau_mot_de_passe"])
        user.save()
        membre = user.membre
        membre.mot_de_passe_a_changer = False
        membre.save(update_fields=["mot_de_passe_a_changer"])


class UtilisateurAdminSerializer(serializers.ModelSerializer):
    """Pour la création et la gestion d'un utilisateur par l'admin."""
    role = serializers.ChoiceField(choices=[])  # choices injectées dynamiquement
    mot_de_passe = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Utilisateur
        fields = ["id", "username", "first_name", "last_name", "email", "role", "mot_de_passe"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.conf import settings
        self.fields["role"].choices = list(ROLES.get(settings.ERP_TYPE, {}).keys())

    def create(self, validated_data):
        from django.conf import settings
        role = validated_data.pop("role")
        mot_de_passe = validated_data.pop("mot_de_passe", None)
        user = Utilisateur(**validated_data)
        if mot_de_passe:
            user.set_password(mot_de_passe)
        else:
            user.set_unusable_password()
        user.save()
        Membre.objects.create(
            utilisateur=user,
            entreprise=settings.ENTREPRISE,
            role=role,
            actif=True,
        )
        return user
