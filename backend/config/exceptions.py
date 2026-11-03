from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger("apps")


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        logger.error("Erreur interne non gérée", exc_info=exc)
        return Response(
            {"detail": "Une erreur interne est survenue. Contactez l'administrateur."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return response
