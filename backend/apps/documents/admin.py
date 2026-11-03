from django.contrib import admin
from .models import BonCommande, DocumentScan, DocumentErp, JournalActivite


@admin.register(BonCommande)
class BonCommandeAdmin(admin.ModelAdmin):
    list_display = ["reference", "fournisseur", "date", "statut_erp"]
    search_fields = ["reference", "fournisseur"]


@admin.register(DocumentScan)
class DocumentScanAdmin(admin.ModelAdmin):
    list_display = ["__str__", "statut_sync", "cree_par", "cree_le"]
    list_filter = ["statut_sync", "type_document"]
    readonly_fields = ["drive_file_id", "drive_link", "cree_le"]


@admin.register(JournalActivite)
class JournalActiviteAdmin(admin.ModelAdmin):
    list_display = ["date", "utilisateur", "action", "bon_commande"]
    list_filter = ["action"]
    readonly_fields = ["utilisateur", "action", "bon_commande", "detail", "date"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
