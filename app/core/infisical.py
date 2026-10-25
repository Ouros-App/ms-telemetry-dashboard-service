import os

from dotenv import load_dotenv
from infisical_sdk import InfisicalSDKClient

DEFAULT_INFISICAL_SITE_URL = "https://app.infisical.com"

_REQUIRED_INFISICAL_KEYS = (
    "INFISICAL_CLIENT_ID",
    "INFISICAL_CLIENT_SECRET",
    "INFISICAL_PROJECT_ID",
    "INFISICAL_ENVIRONMENT",
    "INFISICAL_SECRET_PATH",
)


def load_infisical_secrets() -> None:
    """Load runtime secrets from Infisical using Ouros Universal Auth (Machine Identity)."""

    load_dotenv(override=False)

    client_id = os.getenv("INFISICAL_CLIENT_ID")
    client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
    project_id = os.getenv("INFISICAL_PROJECT_ID")
    environment = os.getenv("INFISICAL_ENVIRONMENT") or os.getenv("INFISICAL_ENV")
    secret_path = os.getenv("INFISICAL_SECRET_PATH") or os.getenv("INFISICAL_PATH")
    site_url = (
        os.getenv("INFISICAL_SITE_URL")
        or os.getenv("INFISICAL_HOST")
        or DEFAULT_INFISICAL_SITE_URL
    )

    provided = (client_id, client_secret, project_id, environment, secret_path)
    if not any(provided):
        return

    missing = []
    if not client_id:
        missing.append("INFISICAL_CLIENT_ID")
    if not client_secret:
        missing.append("INFISICAL_CLIENT_SECRET")
    if not project_id:
        missing.append("INFISICAL_PROJECT_ID")
    if not environment:
        missing.append("INFISICAL_ENVIRONMENT")
    if not secret_path:
        missing.append("INFISICAL_SECRET_PATH")

    if missing:
        raise RuntimeError(
            "Configuração parcial do Infisical; faltando: " + ", ".join(missing)
        )

    if environment not in {"prod", "dev"}:
        raise RuntimeError("INFISICAL_ENVIRONMENT deve ser 'prod' ou 'dev'")

    client = InfisicalSDKClient(host=site_url)
    client.auth.universal_auth.login(
        client_id=client_id,
        client_secret=client_secret,
    )

    response = client.secrets.list_secrets(
        project_id=project_id,
        environment_slug=environment,
        secret_path=secret_path,
        view_secret_value=True,
    )

    for secret in response.secrets:
        os.environ[secret.secretKey] = secret.secretValue
