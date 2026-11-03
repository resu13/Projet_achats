"""
Service Google Drive — Upload, gestion des dossiers, téléchargement.

Sécurité :
  - Utilise le compte de service propre à l'entreprise (GOOGLE_KEY_FILE).
  - Accès limité au dossier racine de l'entreprise (DRIVE_FOLDER_ID).
  - Noms de fichiers nettoyés avant upload.
  - Retry automatique (3 tentatives) sur les erreurs réseau.
  - Aucun secret loggé.
"""
from __future__ import annotations

import hashlib
import io
import logging
import mimetypes
import os
import re
import time
import uuid
from pathlib import Path
from typing import BinaryIO

from google.auth.exceptions import GoogleAuthError, TransportError
import httplib2
from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
MAX_RETRIES = 3
RETRY_DELAY = 2  # secondes entre les tentatives
HTTP_RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
NETWORK_ERRORS = (OSError, TimeoutError, httplib2.HttpLib2Error, TransportError)

# Types MIME autorisés pour l'upload
MIME_AUTORISES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}

# Extension → MIME attendu (validation MIME réelle côté backend)
EXTENSIONS_AUTORISEES = {".pdf", ".jpg", ".jpeg", ".png"}


class DriveIndisponibleError(Exception):
    """Google Drive est inaccessible."""

class FichierInvalideError(Exception):
    """Le fichier échoue à la validation (type MIME, taille, nom)."""


def _executer_avec_reprises(operation):
    for tentative in range(1, MAX_RETRIES + 1):
        try:
            return operation()
        except HttpError as exc:
            if exc.status_code not in HTTP_RETRY_STATUSES or tentative == MAX_RETRIES:
                raise
            logger.warning(
                "Tentative Drive %d/%d échouée (HTTP %s). Nouvelle tentative dans %ds.",
                tentative,
                MAX_RETRIES,
                exc.status_code,
                RETRY_DELAY * tentative,
            )
        except NETWORK_ERRORS:
            if tentative == MAX_RETRIES:
                raise
            logger.warning(
                "Tentative Drive %d/%d échouée (erreur réseau). Nouvelle tentative dans %ds.",
                tentative,
                MAX_RETRIES,
                RETRY_DELAY * tentative,
            )
        time.sleep(RETRY_DELAY * tentative)


def _nettoyer_nom(nom: str) -> str:
    """Supprime les caractères dangereux du nom de fichier."""
    nom = Path(nom).name  # Supprime les chemins
    nom = re.sub(r"[^\w\s\-.]", "_", nom, flags=re.UNICODE)
    nom = nom[:200]  # Limite la longueur
    return nom or "document"


def _verifier_mime_reel(contenu: bytes) -> str:
    """Vérifie le type MIME réel par les magic bytes (non par l'extension)."""
    if contenu[:4] == b"%PDF":
        return "application/pdf"
    if contenu[:3] in (b"\xff\xd8\xff",):
        return "image/jpeg"
    if contenu[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "application/octet-stream"


def valider_fichier(contenu: bytes, nom_fichier: str) -> str:
    """
    Valide le contenu et le nom d'un fichier à uploader.
    Retourne le type MIME réel.
    Lève FichierInvalideError en cas d'échec.
    """
    taille_max = getattr(settings, "TAILLE_MAX_FICHIER_OCTETS", 20 * 1024 * 1024)
    if len(contenu) > taille_max:
        taille_mo = taille_max // (1024 * 1024)
        raise FichierInvalideError(
            f"Le fichier est trop volumineux. Taille maximale : {taille_mo} Mo."
        )

    if len(contenu) == 0:
        raise FichierInvalideError("Le fichier est vide.")

    ext = Path(nom_fichier).suffix.lower()
    if ext not in EXTENSIONS_AUTORISEES:
        raise FichierInvalideError(
            f"Extension '{ext}' non autorisée. Formats acceptés : PDF, JPEG, PNG."
        )

    mime_reel = _verifier_mime_reel(contenu)
    if mime_reel not in MIME_AUTORISES:
        raise FichierInvalideError(
            "Le type réel du fichier n'est pas autorisé. "
            "Seuls les formats PDF, JPEG et PNG sont acceptés."
        )
    return mime_reel


class DriveService:
    """Service Google Drive pour l'application achats."""

    def __init__(self):
        key_file = settings.GOOGLE_KEY_FILE
        if not os.path.isfile(key_file):
            raise DriveIndisponibleError(
                f"Fichier de clé Google introuvable : {key_file}"
            )
        self._root_folder_id = settings.DRIVE_FOLDER_ID
        if not self._root_folder_id:
            raise DriveIndisponibleError("Le dossier racine Google Drive n’est pas configuré.")
        try:
            credentials = service_account.Credentials.from_service_account_file(
                key_file, scopes=SCOPES
            )
            self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        except (GoogleAuthError, OSError, ValueError) as exc:
            logger.error("Chargement de la configuration Google Drive impossible (%s).", type(exc).__name__)
            raise DriveIndisponibleError(
                "La configuration du compte de service Google Drive est invalide."
            ) from exc

    def verifier_connexion(self) -> None:
        """Vérifie que le compte de service peut lire le dossier racine."""
        try:
            _executer_avec_reprises(
                lambda: self._service.files().get(
                    fileId=self._root_folder_id,
                    fields="id",
                ).execute()
            )
        except HttpError as exc:
            logger.warning("Vérification Drive échouée (HTTP %s).", exc.status_code)
            raise DriveIndisponibleError(
                "Google Drive est inaccessible ou le dossier racine n’est pas partagé avec le compte de service."
            ) from exc
        except NETWORK_ERRORS as exc:
            logger.warning("Vérification Drive échouée (erreur réseau).")
            raise DriveIndisponibleError("Google Drive est inaccessible.") from exc

    # ── Dossiers ──────────────────────────────────────────────────────────────

    def _trouver_ou_creer_dossier(self, nom: str, parent_id: str) -> str:
        """
        Retourne l'ID d'un sous-dossier existant ou le crée.
        Opération idempotente.
        """
        nom_nettoye = _nettoyer_nom(nom)
        query = (
            f"name='{nom_nettoye}' and "
            f"'{parent_id}' in parents and "
            "mimeType='application/vnd.google-apps.folder' and "
            "trashed=false"
        )
        def trouver_ou_creer():
            resultats = (
                self._service.files()
                .list(q=query, fields="files(id, name)", spaces="drive")
                .execute()
            )
            fichiers = resultats.get("files", [])
            if fichiers:
                return fichiers[0]["id"]

            # Créer le dossier
            metadata = {
                "name": nom_nettoye,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            dossier = (
                self._service.files()
                .create(body=metadata, fields="id")
                .execute()
            )
            return dossier["id"]

        try:
            return _executer_avec_reprises(trouver_ou_creer)
        except HttpError as exc:
            logger.error("Erreur Drive lors de la gestion du dossier '%s' : %s", nom, exc.status_code)
            raise DriveIndisponibleError("Impossible d'accéder à Google Drive.") from exc
        except NETWORK_ERRORS as exc:
            logger.error("Erreur réseau Drive lors de la gestion du dossier '%s'.", nom)
            raise DriveIndisponibleError("Impossible d'accéder à Google Drive.") from exc

    def obtenir_dossier_bc(self, reference_bc: str, type_document: str) -> str:
        """
        Retourne l'ID du dossier Drive : RACINE/BC/reference_bc/type_document.
        Crée les dossiers manquants.
        """
        dossier_bc_root = self._trouver_ou_creer_dossier("BC", self._root_folder_id)
        dossier_bc = self._trouver_ou_creer_dossier(reference_bc, dossier_bc_root)
        dossier_type = self._trouver_ou_creer_dossier(type_document, dossier_bc)
        return dossier_type

    # ── Upload ────────────────────────────────────────────────────────────────

    def uploader_fichier(
        self,
        contenu: bytes,
        nom_fichier: str,
        mime_type: str,
        dossier_id: str,
    ) -> tuple[str, str]:
        """
        Upload un fichier sur Drive.
        Retourne (file_id, lien_view).
        Retry automatique 3 fois sur erreur réseau.
        """
        nom_nettoye = _nettoyer_nom(nom_fichier)
        upload_key = uuid.uuid4().hex
        metadata = {
            "name": nom_nettoye,
            "parents": [dossier_id],
            "appProperties": {"scanUploadId": upload_key},
        }

        derniere_erreur = None
        for tentative in range(1, MAX_RETRIES + 1):
            try:
                fichier_existant = (
                    self._service.files()
                    .list(
                        q=(
                            "appProperties has { key='scanUploadId' "
                            f"and value='{upload_key}' }} and trashed=false"
                        ),
                        fields="files(id, webViewLink)",
                        spaces="drive",
                    )
                    .execute()
                    .get("files", [])
                )
                if fichier_existant:
                    fichier = fichier_existant[0]
                    file_id = fichier["id"]
                    lien = fichier.get(
                        "webViewLink",
                        f"https://drive.google.com/file/d/{file_id}/view",
                    )
                    return file_id, lien

                media = MediaIoBaseUpload(
                    io.BytesIO(contenu), mimetype=mime_type, resumable=True
                )
                fichier = (
                    self._service.files()
                    .create(body=metadata, media_body=media, fields="id, webViewLink")
                    .execute()
                )
                file_id = fichier["id"]
                lien = fichier.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")
                logger.info("Fichier uploadé sur Drive : %s", file_id)
                return file_id, lien
            except HttpError as exc:
                derniere_erreur = exc
                if tentative < MAX_RETRIES and exc.status_code in (
                    408, 429, 500, 502, 503, 504
                ):
                    logger.warning(
                        "Tentative %d/%d échouée (HTTP %s). Nouvelle tentative dans %ds.",
                        tentative, MAX_RETRIES, exc.status_code, RETRY_DELAY * tentative,
                    )
                    time.sleep(RETRY_DELAY * tentative)
                else:
                    break
            except (
                OSError,
                TimeoutError,
                httplib2.HttpLib2Error,
                TransportError,
            ) as exc:
                derniere_erreur = exc
                if tentative < MAX_RETRIES:
                    logger.warning(
                        "Tentative %d/%d échouée (erreur réseau). Nouvelle tentative dans %ds.",
                        tentative,
                        MAX_RETRIES,
                        RETRY_DELAY * tentative,
                    )
                    time.sleep(RETRY_DELAY * tentative)
                else:
                    break
            except Exception as exc:
                derniere_erreur = exc
                break

        logger.error("Upload Drive échoué après %d tentatives.", MAX_RETRIES)
        raise DriveIndisponibleError(
            "Impossible d'envoyer le fichier sur Google Drive. Réessayez plus tard."
        ) from derniere_erreur

    # ── Téléchargement ───────────────────────────────────────────────────────

    def telecharger_fichier(self, file_id: str) -> bytes:
        """Télécharge un fichier depuis Drive. Utilisé pour le re-download des PDF de BR."""
        def telecharger():
            request = self._service.files().get_media(fileId=file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buffer.getvalue()

        try:
            return _executer_avec_reprises(telecharger)
        except HttpError as exc:
            logger.error("Téléchargement Drive échoué (file_id=%s) : %s", file_id, exc.status_code)
            raise DriveIndisponibleError("Impossible de télécharger le fichier depuis Drive.") from exc
        except NETWORK_ERRORS as exc:
            logger.error("Téléchargement Drive échoué (erreur réseau, file_id=%s).", file_id)
            raise DriveIndisponibleError("Impossible de télécharger le fichier depuis Drive.") from exc

    # ── Suppression ──────────────────────────────────────────────────────────

    def supprimer_fichier(self, file_id: str) -> None:
        """Supprime un fichier Drive (utilisé lors du remplacement d'un scan)."""
        try:
            _executer_avec_reprises(
                lambda: self._service.files().delete(fileId=file_id).execute()
            )
            logger.info("Fichier Drive supprimé : %s", file_id)
        except HttpError as exc:
            if exc.status_code == 404:
                logger.info("Fichier Drive déjà absent : %s", file_id)
                return
            logger.error("Suppression Drive échouée (HTTP %s).", exc.status_code)
            raise DriveIndisponibleError(
                "Impossible de supprimer le fichier dans Google Drive."
            ) from exc
        except NETWORK_ERRORS as exc:
            logger.error("Suppression Drive échouée (erreur réseau).")
            raise DriveIndisponibleError(
                "Impossible de supprimer le fichier dans Google Drive."
            ) from exc


# ── Singleton (une instance par processus) ────────────────────────────────────

_drive_service: DriveService | None = None


def get_drive_service() -> DriveService:
    global _drive_service
    if _drive_service is None:
        _drive_service = DriveService()
    return _drive_service
