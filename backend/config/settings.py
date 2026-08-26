"""
Django settings for config project.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
env_file = BASE_DIR.parent / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-dev-key-change-me")

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "courts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
#
# Local dev (and the docker-compose `db` service) use the broken-out
# POSTGRES_* vars below -- no DATABASE_URL is set locally, so this branch
# is untouched by the production path. A managed Postgres provider (e.g.
# Render) instead hands you one connection string via DATABASE_URL; when
# that's present it takes over entirely and SSL is required, since that's
# what such providers expect for external connections.
database_url = env("DATABASE_URL", default=None)
if database_url:
    DATABASES = {"default": env.db_url_config(database_url)}
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].setdefault("sslmode", "require")
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="court_signup"),
            "USER": env("POSTGRES_USER", default="court_signup"),
            "PASSWORD": env("POSTGRES_PASSWORD", default="court_signup"),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
        }
    }


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization

LANGUAGE_CODE = "en-us"

TIME_ZONE = "America/Los_Angeles"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# WhiteNoise serves these directly from the Django process -- no separate
# static host/CDN needed. Safe to enable unconditionally: it works the
# same whether DEBUG is True or False, so local dev is unaffected.

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "courts.authentication.PlayerSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# CORS - allow the local Vite dev server (and, once set, a real frontend origin)
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173", "http://localhost:5183"]
)

# Required by Django for cross-origin CSRF-protected requests once the
# frontend and backend are on different HTTPS origins. Empty by default --
# harmless locally, since the dev server never needs it.
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# Only trust the X-Forwarded-Proto header from a reverse proxy when
# explicitly told to -- a host that ISN'T actually behind a proxy setting
# this header would let a client spoof "I'm HTTPS" and defeat
# SECURE_SSL_REDIRECT below, so this is opt-in, not assumed. Render/
# Railway/Fly-style platforms terminate TLS at a proxy and need this on.
if env.bool("DJANGO_TRUST_PROXY_HEADER", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HTTPS-only hardening, off by default so local HTTP dev keeps working
# with zero required env changes. Turn on with DJANGO_SECURE=True once
# actually serving over HTTPS.
if env.bool("DJANGO_SECURE", default=False):
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Plain console logging -- sufficient for a platform (Render, etc.) that
# captures stdout/stderr as its log stream. Django's own bare defaults
# would otherwise only surface 5xx errors via AdminEmailHandler (which
# needs SMTP configured) instead of just printing them where the host
# already looks for logs.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# --- Court signup app settings ---
# Single source of truth for the business-rule constants used across
# courts/models.py, courts/serializers.py, and courts/services.py.
COURT_CAPACITY_DEFAULT = 4
# Normal session length for a fresh activation -- unrelated to (and
# renamed away from "reservation" to avoid colliding with) a Court's own
# admin-set reservation window (Court.reservation_start/end).
SESSION_DURATION_MINUTES = 45
ALLOWED_GROUP_SIZES = (2, 4)
