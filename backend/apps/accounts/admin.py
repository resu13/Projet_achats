from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Utilisateur, Membre


class MembreInline(admin.StackedInline):
    model = Membre
    extra = 0


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    inlines = [MembreInline]
    list_display = ["username", "get_full_name", "email", "is_active"]


@admin.register(Membre)
class MembreAdmin(admin.ModelAdmin):
    list_display = ["utilisateur", "entreprise", "role", "actif"]
    list_filter = ["role", "actif", "entreprise"]
