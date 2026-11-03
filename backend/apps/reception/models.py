"""
Modèles pour la génération des Bons de Réception (Urium uniquement).

Modèles :
  - LigneBonCommande : lignes du BC lues depuis Urium
  - BonReception     : BR généré par l'application, avec cycle brouillon → validé → annulé
  - LigneReception   : quantités reçues par ligne de BC

Numérotation séquentielle :
  Format BR-AAAA-NNNN, attribuée à la validation de façon atomique
  (SELECT FOR UPDATE sur un compteur annuel) pour garantir l'absence de trou
  même en cas d'accès concurrent.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from django.db import models, transaction
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.documents.models import BonCommande, DocumentScan


# ─── Compteur annuel pour la numérotation ────────────────────────────────────

class CompteurBR(models.Model):
    """
    Compteur par année pour la numérotation séquentielle des BR.
    Utilisé avec SELECT FOR UPDATE pour garantir l'atomicité.
    """
    annee = models.IntegerField(unique=True)
    dernier_numero = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Compteur BR"

    @classmethod
    def prochain_numero(cls, annee: int) -> str:
        """
        Retourne le prochain numéro au format BR-AAAA-NNNN.
        DOIT être appelé dans une transaction avec SELECT FOR UPDATE.
        """
        compteur, _ = cls.objects.select_for_update().get_or_create(
            annee=annee, defaults={"dernier_numero": 0}
        )
        compteur.dernier_numero += 1
        compteur.save(update_fields=["dernier_numero"])
        return f"BR-{annee}-{compteur.dernier_numero:04d}"


# ─── Lignes du Bon de Commande ────────────────────────────────────────────────

class LigneBonCommande(models.Model):
    """
    Ligne d'un BC lue depuis l'ERP Urium.
    Mise à jour lors de la synchronisation du BC.
    """
    bon_commande = models.ForeignKey(
        BonCommande, on_delete=models.CASCADE, related_name="lignes"
    )
    code_article = models.CharField(max_length=100, blank=True)
    designation = models.CharField(max_length=500)
    unite = models.CharField(max_length=20, blank=True)
    quantite_commandee = models.DecimalField(max_digits=14, decimal_places=4)
    ordre = models.PositiveSmallIntegerField(default=0, help_text="Ordre d'affichage")
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Ligne de BC"
        verbose_name_plural = "Lignes de BC"
        ordering = ["ordre", "id"]

    def __str__(self):
        return f"{self.code_article} — {self.designation}"

    @property
    def quantite_deja_recue(self) -> Decimal:
        """Somme des quantités reçues dans les BR VALIDÉS uniquement."""
        from django.db.models import Sum
        from django.db.models.functions import Coalesce
        result = LigneReception.objects.filter(
            ligne_bon_commande=self,
            bon_reception__statut=BonReception.STATUT_VALIDE,
        ).aggregate(total=Coalesce(Sum("quantite_recue"), Decimal("0")))
        return result["total"]

    @property
    def reste_a_recevoir(self) -> Decimal:
        return max(Decimal("0"), self.quantite_commandee - self.quantite_deja_recue)


# ─── Bon de Réception ─────────────────────────────────────────────────────────

class BonReception(models.Model):
    STATUT_BROUILLON = "brouillon"
    STATUT_VALIDE = "valide"
    STATUT_ANNULE = "annule"
    STATUT_CHOICES = [
        (STATUT_BROUILLON, "Brouillon"),
        (STATUT_VALIDE, "Validé"),
        (STATUT_ANNULE, "Annulé"),
    ]

    bon_commande = models.ForeignKey(
        BonCommande, on_delete=models.PROTECT, related_name="bons_reception"
    )
    numero = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        help_text="Format BR-AAAA-NNNN, attribué à la validation",
    )
    date_reception = models.DateField(default=timezone.now)
    numero_bl_fournisseur = models.CharField(
        max_length=100, blank=True, help_text="Numéro du BL fournisseur (optionnel)"
    )
    bl_lie = models.ForeignKey(
        DocumentScan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bons_reception",
        limit_choices_to={"type_document": DocumentScan.TYPE_BL},
        help_text="Lien optionnel vers un BL scanné",
    )
    remarques = models.TextField(blank=True)
    statut = models.CharField(
        max_length=10, choices=STATUT_CHOICES, default=STATUT_BROUILLON, db_index=True
    )
    motif_annulation = models.TextField(blank=True)

    # Champs de validation (renseignés à la validation, immuables ensuite)
    cree_par = models.ForeignKey(
        Utilisateur, on_delete=models.PROTECT, related_name="bons_reception_crees"
    )
    valide_par = models.ForeignKey(
        Utilisateur,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="bons_reception_valides",
    )
    valide_le = models.DateTimeField(null=True, blank=True)
    nom_receptionnaire = models.CharField(
        max_length=255, blank=True,
        help_text="Copie du nom et rôle au moment de la validation"
    )
    adresse_ip_validation = models.GenericIPAddressField(null=True, blank=True)

    # PDF
    empreinte_sha256 = models.CharField(max_length=64, blank=True)
    drive_file_id = models.CharField(max_length=200, blank=True)
    drive_link = models.URLField(max_length=500, blank=True)

    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bon de réception"
        verbose_name_plural = "Bons de réception"
        ordering = ["-cree_le"]
        indexes = [
            models.Index(fields=["bon_commande", "statut"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["numero"],
                condition=~models.Q(numero=""),
                name="unicite_numero_br",
            )
        ]

    def __str__(self):
        return self.numero or f"BR brouillon #{self.pk}"

    @property
    def est_modifiable(self) -> bool:
        return self.statut == self.STATUT_BROUILLON


# ─── Ligne de Réception ───────────────────────────────────────────────────────

class LigneReception(models.Model):
    bon_reception = models.ForeignKey(
        BonReception, on_delete=models.CASCADE, related_name="lignes"
    )
    ligne_bon_commande = models.ForeignKey(
        LigneBonCommande, on_delete=models.PROTECT, related_name="lignes_reception"
    )
    quantite_recue = models.DecimalField(max_digits=14, decimal_places=4)
    remarque_ligne = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "Ligne de réception"
        verbose_name_plural = "Lignes de réception"
        unique_together = [("bon_reception", "ligne_bon_commande")]

    def __str__(self):
        return (
            f"{self.ligne_bon_commande.designation} × {self.quantite_recue} "
            f"({self.bon_reception})"
        )
