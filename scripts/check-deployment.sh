#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

ENV_FILE=${1:?Usage: scripts/check-deployment.sh .env.odoo_co}
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
# Deployment env files must contain assignments only; never execute arbitrary shell commands.
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  if [[ ! "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
    echo "Invalid environment assignment in $ENV_FILE." >&2
    exit 1
  fi
  key=${line%%=*}
  value=${line#*=}
  value=${value%$'\r'}
  printf -v "$key" '%s' "$value"
  export "$key"
done < "$ENV_FILE"
set +a

for name in COMPOSE_PROJECT_NAME SECRET_KEY ALLOWED_HOSTS DB_NAME DB_USER DB_PASSWORD ERP_TYPE \
  DRIVE_FOLDER_ID GOOGLE_KEY_FILE_SOURCE TLS_CERT_FILE_SOURCE TLS_KEY_FILE_SOURCE \
  NOM_ENTREPRISE; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required setting $name is empty." >&2
    exit 1
  fi
done
if [[ ! "$COMPOSE_PROJECT_NAME" =~ ^[a-z0-9_-]+$ ]]; then
  echo "COMPOSE_PROJECT_NAME must be a unique lowercase project identifier." >&2
  exit 1
fi

if [[ "$DEBUG" != "False" && "$DEBUG" != "false" ]]; then
  echo "DEBUG must be False for production." >&2
  exit 1
fi
if [[ ${#SECRET_KEY} -lt 50 || "$SECRET_KEY" == *changez* || "$SECRET_KEY" == *dev-secret* ]]; then
  echo "SECRET_KEY must be a unique, generated value of at least 50 characters." >&2
  exit 1
fi
if [[ ${#DB_PASSWORD} -lt 20 || "$DB_PASSWORD" == *mot-de-passe* || "$DB_PASSWORD" == postgres* ]]; then
  echo "DB_PASSWORD must be a unique value of at least 20 characters." >&2
  exit 1
fi
if [[ "$ALLOWED_HOSTS" == *localhost* || "$ALLOWED_HOSTS" == *example* || "$ALLOWED_HOSTS" == *votre-* || "$ALLOWED_HOSTS" == *'*'* ]]; then
  echo "ALLOWED_HOSTS must contain only the real production hostnames." >&2
  exit 1
fi

for file in "$GOOGLE_KEY_FILE_SOURCE" "$TLS_CERT_FILE_SOURCE" "$TLS_KEY_FILE_SOURCE"; do
  if [[ ! -f "$file" || ! -r "$file" ]]; then
    echo "Required secret/certificate file is missing or unreadable: $file" >&2
    exit 1
  fi
done

if ! python -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); assert d.get("type") == "service_account"' "$GOOGLE_KEY_FILE_SOURCE"; then
  echo "The Google credentials file is not a valid service-account JSON." >&2
  exit 1
fi

openssl x509 -in "$TLS_CERT_FILE_SOURCE" -noout >/dev/null
IFS=, read -ra hostnames <<< "$ALLOWED_HOSTS"
for hostname in "${hostnames[@]}"; do
  openssl x509 -in "$TLS_CERT_FILE_SOURCE" -noout -checkhost "${hostname// /}" >/dev/null
done
openssl pkey -in "$TLS_KEY_FILE_SOURCE" -passin pass: -noout >/dev/null
cert_public_key=$(openssl x509 -in "$TLS_CERT_FILE_SOURCE" -pubkey -noout | openssl pkey -pubin -outform DER | openssl dgst -sha256)
private_public_key=$(openssl pkey -in "$TLS_KEY_FILE_SOURCE" -passin pass: -pubout -outform DER | openssl dgst -sha256)
if [[ "$cert_public_key" != "$private_public_key" ]]; then
  echo "The TLS certificate and private key do not match." >&2
  exit 1
fi
if [[ "$ERP_TYPE" == "odoo" ]]; then
  for name in ODOO_URL ODOO_DB ODOO_USER ODOO_KEY; do
    if [[ -z "${!name:-}" || "${!name}" == *votre-* ]]; then
      echo "Required Odoo setting $name is empty or still a sample value." >&2
      exit 1
    fi
  done
elif [[ "$ERP_TYPE" != "urium" ]]; then
  echo "ERP_TYPE must be odoo or urium." >&2
  exit 1
fi

docker compose --env-file "$ENV_FILE" config --quiet
echo "Deployment configuration and mounted credentials are structurally valid."
if [[ "$ERP_TYPE" == "urium" ]]; then
  echo "WARNING: Urium REST routes/authentication are not defined; ERP purchase-order operations will remain unavailable." >&2
fi
