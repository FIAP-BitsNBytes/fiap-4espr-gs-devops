"""Ponto de entrada do gunicorn (App Service): gunicorn wsgi:app"""
import os

# A telemetria precisa ser configurada antes de o Flask ser importado.
if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor()

from app import create_app  # noqa: E402

app = create_app()
