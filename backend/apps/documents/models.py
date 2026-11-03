from django.db import models
from django.conf import settings
from apps.accounts.models import Utilisateur


class BonCommande(models.Model):
    """Copie locale légère lue depuis l'ERP."""
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    fournisseur = models.CharField(max_length=255)
    date = models.DateField(null=True, blank=True)
    statut_erp = models.CharField(max_length=50, blank=True)
    montant = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    devise = models.CharField(max_length=10, blank=True)
    derniere_synchro = models.DateTimeField(null=True, blank=True)
    erp_id = models.CharField(max_length=100, blank=True, help_text="ID dans l'ERP source")

    class Meta:
        verbose_name = "Bon de commande"
        verbose_name_plural = "Bons de commande"
        ordering = ["-date"]

    def __str__(self):
        return self.reference

    @property
    def statut_reception(self):
        """non_recu | partiellement_recu | entierement_recu (Urium uniquement)."""
        if settings.ERP_TYPE != "urium":
            return None
        lignes = self.lignes.filter(actif=True)
        if not lignes.exists():
            return "non_recu"
        totaux = [
            (l.quantite_commandee, l.quantite_deja_recue) for l in lignes
        ]
        recus = sum(r for _, r in totaux)
        commandes = sum(c for c, _ in totaux)
        if recus == 0:
            return "non_recu"
        if recus >= commandes:
            return "entierement_recu"
        return "partiellement_recu"


class DocumentScan(models.Model):
    """Document physique scanné et stocké sur Drive."""
    TYPE_BL = "BL"
    TYPE_FACTURE = "FACTURE"
    TYPE_CHOICES = [(TYPE_BL, "Bon de livraison"), (TYPE_FACTURE, "Facture")]

    STATUT_EN_ATTENTE = "en_attente"
    STATUT_SYNCHRONISE = "synchronise"
    STATUT_ECHEC = "echec"
    STATUT_NON_APPLICABLE = "non_applicable"
    STATUT_CHOICES = [
        (STATUT_EN_ATTENTE, "En attente"),
        (STATUT_SYNCHRONISE, "Synchronisé"),
        (STATUT_ECHEC, "Échec"),
        (STATUT_NON_APPLICABLE, "Non applicable"),
    ]

    bon_commande = models.ForeignKey(
        BonCommande, on_delete=models.PROTECT, related_name="documents"
    )
    bons_commande_lies = models.ManyToManyField(
        BonCommande, related_name="documents_lies", blank=True
    )
    type_document = models.CharField(max_length=10, choices=TYPE_CHOICES)
    numero_document = models.CharField(
        max_length=100, help_text="Numéro du document fournisseur"
    )
    nom_fichier = models.CharField(max_length=255)
    drive_file_id = models.CharField(max_length=200, blank=True)
    drive_link = models.URLField(max_length=500, blank=True)
    statut_sync = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default=STATUT_EN_ATTENTE
    )
    message_erreur = models.TextField(blank=True)
    cree_par = models.ForeignKey(
        Utilisateur, on_delete=models.PROTECT, related_name="documents_scannés"
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    remplace_par = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="remplace",
    )

    class Meta:
        verbose_name = "Document scanné"
        verbose_name_plural = "Documents scannés"
        constraints = [
            models.UniqueConstraint(
                fields=["bon_commande", "type_document", "numero_document"],
                name="unicite_document_bc",
                violation_error_message="Un document de ce type avec ce numéro existe déjà pour ce bon de commande.",
            )
        ]
        indexes = [
            models.Index(fields=["bon_commande", "cree_le"]),
            models.Index(fields=["statut_sync"]),
        ]
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.type_document} {self.numero_document} — {self.bon_commande.reference}"

    @property
    def bons_commande_associes(self):
        associes = list(self.bons_commande_lies.order_by("pk"))
        if self.bon_commande_id not in {bc.pk for bc in associes}:
            associes.insert(0, self.bon_commande)
        return associes


class DocumentErp(models.Model):
    """BR lus depuis Odoo (lecture seule, jamais modifiés par l'application)."""
    bon_commande = models.ForeignKey(
        BonCommande, on_delete=models.CASCADE, related_name="documents_erp"
    )
    type_document = models.CharField(max_length=20, default="BR")
    reference_erp = models.CharField(max_length=100)
    date_document = models.DateField(null=True, blank=True)
    statut_erp = models.CharField(max_length=50, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    derniere_synchro = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Document ERP"
        verbose_name_plural = "Documents ERP"
        unique_together = [("bon_commande", "reference_erp")]

    def __str__(self):
        return f"{self.type_document} {self.reference_erp}"


class JournalActivite(models.Model):
    """Trace non modifiable de toutes les actions significatives."""
    ACTION_SCAN = "scan"
    ACTION_REMPLACEMENT = "remplacement"
    ACTION_SUPPRESSION = "suppression"
    ACTION_RESYNC = "resynchronisation"
    ACTION_CREATION_BR = "creation_br"
    ACTION_VALIDATION_BR = "validation_br"
    ACTION_ANNULATION_BR = "annulation_br"
    ACTION_CONNEXION = "connexion"
    ACTION_GESTION_USER = "gestion_utilisateur"

    ACTION_CHOICES = [
        (ACTION_SCAN, "Scan"),
        (ACTION_REMPLACEMENT, "Remplacement"),
        (ACTION_SUPPRESSION, "Suppression"),
        (ACTION_RESYNC, "Resynchronisation"),
        (ACTION_CREATION_BR, "Création BR"),
        (ACTION_VALIDATION_BR, "Validation BR"),
        (ACTION_ANNULATION_BR, "Annulation BR"),
        (ACTION_CONNEXION, "Connexion"),
        (ACTION_GESTION_USER, "Gestion utilisateur"),
    ]

    utilisateur = models.ForeignKey(
        Utilisateur,
        null=True,
        on_delete=models.SET_NULL,
        related_name="journal",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    bon_commande = models.ForeignKey(
        BonCommande,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="journal",
    )
    detail = models.TextField(blank=True)
    date = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Journal d'activité"
        verbose_name_plural = "Journal d'activité"
        ordering = ["-date"]
        # Pas de delete/update depuis l'interface : géré par les permissions

    def __str__(self):
        return f"[{self.date:%Y-%m-%d %H:%M}] {self.action} — {self.utilisateur}"
