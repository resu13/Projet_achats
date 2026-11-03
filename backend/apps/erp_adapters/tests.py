from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from . import ErpErreurError, ErpIndisponibleError
from .odoo_adapter import AdaptateurOdoo


@override_settings(
    ODOO_URL="https://odoo.example",
    ODOO_DB="test",
    ODOO_USER="service",
    ODOO_KEY="not-a-real-key",
)
class TestAdaptateurOdoo(SimpleTestCase):
    def test_pousser_document_is_idempotent_after_a_partial_retry(self):
        adapter = AdaptateurOdoo()
        created = {"attachment": False, "message": False}
        lose_message_response = True

        def execute(model, method, *args, **kwargs):
            nonlocal lose_message_response
            if method == "search_read":
                key = "attachment" if model == "ir.attachment" else "message"
                return [{"id": 1}] if created[key] else []
            if model == "ir.attachment":
                created["attachment"] = True
            else:
                created["message"] = True
                if lose_message_response:
                    lose_message_response = False
                    raise ErpIndisponibleError("response lost")

        adapter._execute = Mock(side_effect=execute)
        scan = SimpleNamespace(
            type_document="BL",
            numero_document="BL-001",
            drive_link="https://drive.example/document",
            cree_par=SimpleNamespace(get_full_name=lambda: "Test", username="test"),
            bons_commande_associes=[
                SimpleNamespace(erp_id="42", reference="BC-42")
            ],
        )

        with self.assertRaises(ErpIndisponibleError):
            adapter.pousser_document(scan)
        adapter.pousser_document(scan)

        creates = [
            call.args[:2]
            for call in adapter._execute.call_args_list
            if len(call.args) > 1 and call.args[1] == "create"
        ]
        self.assertCountEqual(
            creates,
            [("ir.attachment", "create"), ("mail.message", "create")],
        )
        self.assertTrue(all(created.values()))

    def test_pousser_document_rejects_non_numeric_erp_ids(self):
        adapter = AdaptateurOdoo()
        adapter._execute = Mock()
        scan = SimpleNamespace(
            type_document="BL",
            numero_document="BL-001",
            drive_link="https://drive.example/document",
            cree_par=SimpleNamespace(get_full_name=lambda: "Test", username="test"),
            bons_commande_associes=[
                SimpleNamespace(erp_id="not-an-id", reference="BC-42")
            ],
        )

        with self.assertRaises(ErpErreurError):
            adapter.pousser_document(scan)

        adapter._execute.assert_not_called()
