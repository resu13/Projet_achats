from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from googleapiclient.errors import HttpError

from services.drive_service import DriveService


class TestDriveUpload(SimpleTestCase):
    def test_upload_reconciles_a_lost_success_response_before_retrying(self):
        drive = DriveService.__new__(DriveService)
        drive._service = Mock()
        files = drive._service.files.return_value
        files.list.return_value.execute.side_effect = [
            {"files": []},
            {"files": [{"id": "drive-id", "webViewLink": "https://drive.example/file"}]},
        ]
        response = Mock(status=503)
        files.create.return_value.execute.side_effect = [
            HttpError(response, b"temporarily unavailable")
        ]

        with patch("services.drive_service.time.sleep"):
            result = drive.uploader_fichier(
                b"%PDF-1.7", "document.pdf", "application/pdf", "folder-id"
            )

        self.assertEqual(result, ("drive-id", "https://drive.example/file"))
        self.assertEqual(files.create.call_count, 1)
        self.assertEqual(files.list.call_count, 2)

    def test_folder_creation_reconciles_a_lost_success_response(self):
        drive = DriveService.__new__(DriveService)
        drive._service = Mock()
        files = drive._service.files.return_value
        files.list.return_value.execute.side_effect = [
            {"files": []},
            {"files": [{"id": "folder-id", "name": "BC-001"}]},
        ]
        response = Mock(status=503)
        files.create.return_value.execute.side_effect = [
            HttpError(response, b"temporarily unavailable")
        ]

        with patch("services.drive_service.time.sleep"):
            result = drive._trouver_ou_creer_dossier("BC-001", "parent-id")

        self.assertEqual(result, "folder-id")
        self.assertEqual(files.create.call_count, 1)
        self.assertEqual(files.list.call_count, 2)

    def test_file_deletion_retries_a_transient_network_failure(self):
        drive = DriveService.__new__(DriveService)
        drive._service = Mock()
        files = drive._service.files.return_value
        files.delete.return_value.execute.side_effect = [TimeoutError(), None]

        with patch("services.drive_service.time.sleep"):
            drive.supprimer_fichier("drive-id")

        self.assertEqual(files.delete.call_count, 2)
