"""
Polaris EMS configuration — spec 018 Wave 1.

Adds SSOT_MODE + per-integration feature flags so each integration can be toggled
independently. Secrets no longer hard-coded — see `app.core.secrets` for the
AWS Parameter Store / Secrets Manager loader (populated on import where
`DEPLOY_ENV` != `local`).
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class SSOTMode(str, Enum):
    """Where EMS sources domain data from.

    * ``strict``   — upstream (MDMS/HES) is the only source of truth. No seeded
                     fallback rows are served. Production default.
    * ``mirror``   — call upstream first; on failure, serve last-cached /
                     seeded rows with an ``x-from-cache: true`` header. Dev
                     demo default.
    * ``disabled`` — fully offline; upstream calls are short-circuited and
                     seeded rows serve every read. Local-laptop default.
    """

    strict = "strict"
    mirror = "mirror"
    disabled = "disabled"


class DeployEnv(str, Enum):
    local = "local"
    dev = "dev"
    staging = "staging"
    prod = "prod"


def _flag_defaults(env: DeployEnv) -> dict:
    """Per-environment feature-flag defaults.

    prod    → all integrations on, strict SSOT
    dev     → all integrations on, mirror SSOT (cached fallback allowed)
    staging → same as dev
    local   → everything off, disabled SSOT (works with a blank Postgres)
    """
    if env in (DeployEnv.prod,):
        return dict(
            SSOT_MODE=SSOTMode.strict,
            HES_ENABLED=True,
            MDMS_ENABLED=True,
            KAFKA_ENABLED=True,
            MDMS_NTL_ENABLED=True,
            TARIFF_INCLINING_ENABLED=True,
            SMART_INVERTER_COMMANDS_ENABLED=True,
            SCHEDULED_REPORTS_ENABLED=True,
        )
    if env in (DeployEnv.dev, DeployEnv.staging):
        return dict(
            SSOT_MODE=SSOTMode.mirror,
            HES_ENABLED=True,
            MDMS_ENABLED=True,
            KAFKA_ENABLED=True,
            MDMS_NTL_ENABLED=True,
            TARIFF_INCLINING_ENABLED=True,
            SMART_INVERTER_COMMANDS_ENABLED=True,
            SCHEDULED_REPORTS_ENABLED=True,
        )
    # local
    return dict(
        SSOT_MODE=SSOTMode.disabled,
        HES_ENABLED=False,
        MDMS_ENABLED=False,
        KAFKA_ENABLED=False,
        MDMS_NTL_ENABLED=False,
        TARIFF_INCLINING_ENABLED=False,
        SMART_INVERTER_COMMANDS_ENABLED=False,
        SCHEDULED_REPORTS_ENABLED=False,
    )


class Settings(BaseSettings):
    APP_NAME: str = "SMOC EMS API"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # ── Deployment context ──
    DEPLOY_ENV: DeployEnv = Field(default=DeployEnv.local, description="local | dev | staging | prod")

    # ── Database / Cache ──
    DATABASE_URL: str = "postgresql://smoc:smoc_pass@db:5432/smoc_ems"
    REDIS_URL: Optional[str] = None  # e.g. redis://redis:6379/0

    # ── JWT Auth ──
    # CAUTION: in dev/prod this MUST be overridden by secrets loader or env var.
    SECRET_KEY: str = "CHANGE-ME-local-only-not-a-real-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # ── CORS ──
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:80",
        "http://frontend:80",
    ]

    # ── SSE / Simulation ──
    SSE_HEARTBEAT_INTERVAL: int = 15
    SIMULATION_TICK_INTERVAL: float = 2.0

    # ── SSOT feature flags (populated by _flag_defaults at load time) ──
    SSOT_MODE: SSOTMode = SSOTMode.disabled
    HES_ENABLED: bool = False
    MDMS_ENABLED: bool = False
    KAFKA_ENABLED: bool = False
    MDMS_NTL_ENABLED: bool = False
    TARIFF_INCLINING_ENABLED: bool = False
    SMART_INVERTER_COMMANDS_ENABLED: bool = False
    SCHEDULED_REPORTS_ENABLED: bool = False

    # ── HES Integration ──
    HES_BASE_URL: str = "http://hes-routing-service.hes.svc.cluster.local:8080"
    HES_API_KEY: Optional[str] = None  # loaded from Secrets Manager in dev/prod
    HES_CONNECT_TIMEOUT_SECONDS: float = 5.0
    HES_READ_TIMEOUT_SECONDS: float = 10.0
    HES_MAX_RETRIES: int = 3
    HES_RETRY_BACKOFF_BASE_MS: int = 100
    HES_BREAKER_FAIL_MAX: int = 5
    HES_BREAKER_RESET_SECONDS: int = 30

    # ── MDMS Integration ──
    MDMS_BASE_URL: str = "http://mdms-api.mdms.svc.cluster.local:8080"
    MDMS_API_KEY: Optional[str] = None
    # Read-only DSN for the MDMS CIS postgres (consumer_master_data). When
    # unset, CIS consumer lookups return empty and the UI falls back to the
    # locally-tagged consumer list. Example:
    #   postgresql+psycopg2://postgres:***@mdms.dev.polagram.in:5432/db_cis
    MDMS_CIS_DB_URL: Optional[str] = None
    # Read-only DSN for the MDMS `validation_rules` postgres. Source for SLA
    # KPIs (Blockload / Daily Load / Billing Profile) via `data_availability`
    # and `profile_types`. When unset the SLA endpoint returns empty metrics
    # rather than 500. Example:
    #   postgresql+psycopg2://postgres:***@mdms.dev.polagram.in:5432/validation_rules
    MDMS_VALIDATION_DB_URL: Optional[str] = None
    # Read-only DSN for the MDMS `gp_hes` postgres. Source for meter push
    # events / alarms (`mdm_pushevent`). When unset the alarm feed falls back
    # to empty rather than 500. Example:
    #   postgresql+psycopg2://postgres:***@mdms.dev.polagram.in:5432/gp_hes
    MDMS_HES_DB_URL: Optional[str] = None
    MDMS_CONNECT_TIMEOUT_SECONDS: float = 5.0
    MDMS_READ_TIMEOUT_SECONDS: float = 10.0
    MDMS_MAX_RETRIES: int = 3
    MDMS_RETRY_BACKOFF_BASE_MS: int = 100
    MDMS_BREAKER_FAIL_MAX: int = 5
    MDMS_BREAKER_RESET_SECONDS: int = 30

    # ── Kafka ──
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"  # SASL_SSL / SASL_PLAINTEXT in dev/prod
    KAFKA_SASL_MECHANISM: Optional[str] = None  # SCRAM-SHA-512 in dev/prod
    KAFKA_SASL_USERNAME: Optional[str] = None
    KAFKA_SASL_PASSWORD: Optional[str] = None
    KAFKA_CONSUMER_GROUP: str = "polaris-ems"
    KAFKA_TOPICS: List[str] = [
        "hesv2.meter.events",
        "hesv2.meter.alarms",
        "hesv2.command.status",
        "hesv2.sensor.readings",
        "hesv2.outage.alerts1",
        "hesv2.network.health",
        "hesv2.der.telemetry",
    ]

    # ── AWS (Parameter Store / Secrets Manager) ──
    AWS_REGION: str = "ap-south-1"
    SECRETS_MANAGER_PREFIX: str = "/polaris-ems"
    # Colon-separated list of SSM paths / secret IDs to preload on startup.
    # e.g.  "/polaris-ems/dev/hes-api-key:/polaris-ems/dev/mdms-api-key:..."
    SECRET_PATHS: str = ""

    # ── Email / SMS / Teams / Firebase / WFM — ALL secrets blank by default ──
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = True
    SMTP_FROM_NAME: str = "SMOC EMS Notifications"
    SMTP_ENABLED: bool = False

    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None  # SECRETS-ONLY
    TWILIO_FROM_NUMBER: Optional[str] = None
    TWILIO_ENABLED: bool = False

    TEAMS_TENANT_ID: Optional[str] = None
    TEAMS_CLIENT_ID: Optional[str] = None
    TEAMS_CLIENT_SECRET: Optional[str] = None  # SECRETS-ONLY
    TEAMS_WEBHOOK_URL: Optional[str] = None
    TEAMS_ENABLED: bool = False

    MAPBOX_ACCESS_TOKEN: Optional[str] = None
    GIS_WMS_BASE_URL: Optional[str] = None
    GIS_ENABLED: bool = False

    FIREBASE_PROJECT_ID: Optional[str] = None
    FIREBASE_SERVER_KEY: Optional[str] = None  # SECRETS-ONLY
    FIREBASE_ENABLED: bool = False

    WFM_BASE_URL: Optional[str] = None
    WFM_API_KEY: Optional[str] = None
    WFM_ENABLED: bool = False

    CIS_BASE_URL: Optional[str] = None
    CIS_API_KEY: Optional[str] = None
    CIS_ENABLED: bool = False

    # ── Spec 018 W3 outage correlator ──
    # Minimum distinct meters reporting power_failure within the window to
    # open an incident. 3 matches the reference implementation in the spec.
    OUTAGE_MIN_METERS: int = 3
    OUTAGE_WINDOW_SECONDS: int = 120
    OUTAGE_DEDUP_WINDOW_SECONDS: int = 1800
    OUTAGE_CORRELATOR_TICK_SECONDS: float = 5.0
    # Nightly reliability_indices_mv refresh (local time).
    RELIABILITY_REFRESH_HOUR: int = 1
    RELIABILITY_REFRESH_MINUTE: int = 0
    # Total customer population used as SAIDI/SAIFI denominator. Can be
    # overridden by the Postgres session GUC `ems.total_customers`.
    RELIABILITY_TOTAL_CUSTOMERS: int = 10000
    # W3.T17 — networked switching. Defaults to OFF outside dev.
    NETWORK_SWITCHING_ENABLED: bool = False

    # ── Spec 018 W4 — alerts / notifications / rule engine ──
    # Alarm-rule engine loop cadence (seconds). Each tick evaluates every
    # active rule against new alarm_event / der_telemetry rows.
    ALARM_RULE_TICK_SECONDS: float = 30.0
    # Default dedup window per rule (seconds) if the rule itself doesn't set
    # one. Prevents a single sustained condition from spamming notifications.
    ALARM_RULE_DEFAULT_DEDUP_SECONDS: int = 300
    # Default escalation acknowledgement SLA (seconds) when a rule's
    # schedule.tiers entry doesn't specify `after_seconds`.
    ALARM_RULE_DEFAULT_ESCALATE_AFTER_SECONDS: int = 300
    # Suppress during quiet hours: channels listed here will be dropped when
    # the wall-clock is inside the rule's quiet_hours window. Email is always
    # queued instead of dropped.
    ALARM_QUIET_SUPPRESS_CHANNELS: List[str] = ["sms", "push"]
    # Master on/off for the background rule engine task.
    ALARM_RULE_ENGINE_ENABLED: bool = True
    # SES region (falls back to AWS_REGION). Email transport chooses SES when
    # `SMTP_USE_SES=True`, otherwise `aiosmtplib` against SMTP_HOST/PORT.
    SMTP_USE_SES: bool = False
    SES_REGION: Optional[str] = None
    # Firebase service-account JSON (raw string, loaded from Secrets Manager).
    # When present, firebase-admin is initialised with this credential.
    FIREBASE_SERVICE_ACCOUNT_JSON: Optional[str] = None

    # ── Spec 018 W2B integrations ──
    # Simulator calls POST /api/v1/der/bulk-import with this bearer token.
    SIMULATOR_API_KEY: Optional[str] = None
    # Spec 018 W3.T14 — scenario proxy target (simulator REST API).
    SIMULATOR_BASE_URL: str = "http://simulator.dev.svc.cluster.local:9200"
    # FOTA image upload: S3 bucket (prod/dev) or local dir fallback for unit tests
    FOTA_S3_BUCKET: Optional[str] = None
    FOTA_S3_REGION: str = "ap-south-1"
    FOTA_PRESIGN_EXPIRY_SECONDS: int = 900
    FOTA_LOCAL_DIR: str = "/tmp/polaris-ems-fota"  # used when FOTA_S3_BUCKET unset
    FOTA_POLL_INTERVAL_SECONDS: int = 15

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # tolerate additional env vars from the pod

    def apply_env_defaults(self) -> "Settings":
        """Merge per-environment flag defaults, only for flags left at their unset state.

        This keeps explicit env-var overrides working: if an operator sets
        ``HES_ENABLED=false`` in dev to debug, we respect it.
        """
        defaults = _flag_defaults(self.DEPLOY_ENV)
        env_set_keys = set(self.model_fields_set)
        for k, v in defaults.items():
            if k not in env_set_keys:
                setattr(self, k, v)
        return self


def _load_settings() -> Settings:
    base = Settings()
    base.apply_env_defaults()
    # Secret overlay (best-effort; never fatal at import time).
    try:
        from app.core.secrets import overlay_secrets  # local import avoids circular
        overlay_secrets(base)
    except Exception:  # pragma: no cover — boto3 missing / IAM denied
        pass
    return base


settings = _load_settings()
