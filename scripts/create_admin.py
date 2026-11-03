#!/usr/bin/env python
"""
Script de création du premier administrateur.
Usage : python scripts/create_admin.py
"""
import os
import sys
import django

# Charge le settings de production
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

# Ajoute le répertoire backend au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
django.setup()

from django.contrib.auth import get_user_model
from apps.accounts.models import Membre
from django.conf import settings
from services.roles import ROLES

Utilisateur = get_user_model()

print("=== Création du premier administrateur ===")
print(f"Entreprise : {settings.ENTREPRISE}")
print(f"ERP        : {settings.ERP_TYPE}")
print()

username = input("Nom d'utilisateur : ").strip()
first_name = input("Prénom : ").strip()
last_name = input("Nom : ").strip()
email = input("Email : ").strip()

import getpass
password = getpass.getpass("Mot de passe : ")
password2 = getpass.getpass("Confirmer le mot de passe : ")

if password != password2:
    print("ERREUR : Les mots de passe ne correspondent pas.")
    sys.exit(1)

if Utilisateur.objects.filter(username=username).exists():
    print(f"ERREUR : L'utilisateur '{username}' existe déjà.")
    sys.exit(1)

try:
    user = Utilisateur.objects.create_superuser(
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
        password=password,
    )
    Membre.objects.create(
        utilisateur=user,
        entreprise=settings.ENTREPRISE,
        role="admin",
        actif=True,
    )
    print()
    print(f"✓ Administrateur '{username}' créé avec succès.")
    print("  RECOMMANDATION : Créez au moins un deuxième administrateur de secours.")
except Exception as e:
    print(f"ERREUR : {e}")
    sys.exit(1)
