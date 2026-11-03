"""
Service de génération PDF pour les Bons de Réception.

Utilise WeasyPrint pour générer un PDF côté serveur à partir d'un template HTML.
Le PDF inclut :
  - En-tête : nom et logo de l'entreprise
  - Numéro et date du BR
  - Référence du BC et fournisseur
  - Numéro de BL fournisseur (si renseigné)
  - Tableau : article / désignation / commandé / déjà reçu / reçu / reste
  - Remarques
  - Mention de validation électronique (non qualifiée)
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db.models import Sum
from django.template.loader import render_to_string
from django.db.models.functions import Coalesce

from apps.reception.models import BonReception, LigneReception

logger = logging.getLogger(__name__)


def generer_pdf_br(bon_reception) -> bytes:
    """
    Génère le PDF d'un BonReception et retourne les octets.
    Le BR doit avoir ses lignes et les données de validation renseignées.
    """
    try:
        from weasyprint import HTML, CSS
    except ImportError as exc:
        raise RuntimeError(
            "WeasyPrint n'est pas installé. Installez-le avec : pip install WeasyPrint"
        ) from exc

    # Préparer les données du contexte
    lignes_detail = []
    for ligne in bon_reception.lignes.select_related("ligne_bon_commande").order_by(
        "ligne_bon_commande__ordre"
    ):
        lbc = ligne.ligne_bon_commande
        received_before = LigneReception.objects.filter(
            ligne_bon_commande=lbc,
            bon_reception__statut=BonReception.STATUT_VALIDE,
        ).exclude(
            bon_reception=bon_reception,
        ).aggregate(
            total=Coalesce(Sum("quantite_recue"), Decimal("0"))
        )["total"]
        lignes_detail.append(
            {
                "code_article": lbc.code_article,
                "designation": lbc.designation,
                "unite": lbc.unite,
                "quantite_commandee": lbc.quantite_commandee,
                "quantite_deja_recue": received_before,
                "quantite_recue": ligne.quantite_recue,
                "reste_a_recevoir": max(
                    0,
                    lbc.quantite_commandee
                    - received_before
                    - ligne.quantite_recue,
                ),
                "remarque_ligne": ligne.remarque_ligne,
            }
        )

    logo_path = getattr(settings, "LOGO_ENTREPRISE", "")
    logo_base64 = ""
    if logo_path and os.path.isfile(logo_path):
        import base64
        with open(logo_path, "rb") as f:
            ext = Path(logo_path).suffix.lower().lstrip(".")
            mime = "image/png" if ext == "png" else "image/jpeg"
            logo_base64 = f"data:{mime};base64,{base64.b64encode(f.read()).decode()}"

    contexte = {
        "br": bon_reception,
        "lignes": lignes_detail,
        "nom_entreprise": getattr(settings, "NOM_ENTREPRISE", settings.ENTREPRISE),
        "logo_base64": logo_base64,
        "date_validation": bon_reception.valide_le,
    }

    html_string = render_to_string("pdf/bon_reception.html", contexte)
    pdf_bytes = HTML(string=html_string, base_url=str(settings.BASE_DIR)).write_pdf()
    return pdf_bytes
