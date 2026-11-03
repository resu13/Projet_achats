from django.urls import path

from .views import BonCommandeDetailView, BonCommandeSearchView, ScanCreateView, ScanListView
from .contract_views import (
    ActivityJournalContractView,
    DashboardContractView,
    PurchaseOrderDetailContractView,
    PurchaseOrderListContractView,
    ScanDetailContractView,
    ScanListContractView,
    ScanResyncContractView,
    ServiceStatusContractView,
)

urlpatterns = [
    path("etat-services", ServiceStatusContractView.as_view(), name="service-status-contract"),
    path("tableau-de-bord", DashboardContractView.as_view(), name="dashboard-contract"),
    path("journal", ActivityJournalContractView.as_view(), name="activity-journal-contract"),
    path("bc", PurchaseOrderListContractView.as_view(), name="bc-contract-list"),
    path("bc/<int:order_id>", PurchaseOrderDetailContractView.as_view(), name="bc-contract-detail"),
    path("scans", ScanListContractView.as_view(), name="scans-contract-list-create"),
    path("scans/<int:scan_id>", ScanDetailContractView.as_view(), name="scans-contract-detail"),
    path("scans/<int:scan_id>/resynchroniser", ScanResyncContractView.as_view(), name="scans-contract-resync"),
    path("documents/bons-commande/", BonCommandeSearchView.as_view(), name="bons-commande-search"),
    path("documents/bons-commande/<str:reference>/", BonCommandeDetailView.as_view(), name="bons-commande-detail"),
    path("documents/scans/", ScanListView.as_view(), name="scans-list"),
    path("documents/scans/ajouter/", ScanCreateView.as_view(), name="scans-create"),
]
