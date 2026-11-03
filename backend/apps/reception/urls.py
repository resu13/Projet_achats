from django.urls import path

from apps.reception.contract_views import (
    ReceiptCancelContractView,
    ReceiptCreateContractView,
    ReceiptDetailContractView,
    ReceiptPdfContractView,
    ReceiptValidateContractView,
)

urlpatterns = [
    path("bc/<int:order_id>/br", ReceiptCreateContractView.as_view(), name="receipt-create"),
    path("br/<int:receipt_id>", ReceiptDetailContractView.as_view(), name="receipt-detail"),
    path("br/<int:receipt_id>/valider", ReceiptValidateContractView.as_view(), name="receipt-validate"),
    path("br/<int:receipt_id>/annuler", ReceiptCancelContractView.as_view(), name="receipt-cancel"),
    path("br/<int:receipt_id>/pdf", ReceiptPdfContractView.as_view(), name="receipt-pdf"),
]
