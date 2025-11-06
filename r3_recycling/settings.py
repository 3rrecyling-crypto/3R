# r3_recycling/settings.py

from pathlib import Path
import os
import dj_database_url

# Base
BASE_DIR = Path(__file__).resolve().parent.parent

# Seguridad
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-eihys(6pm3n+j=(t))*i+c!zj97w#7@@l+=a_w5wm93p3^&r38"
)
DEBUG = os.getenv("DEBUG", "true").lower() == "true"


ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "192.168.10.226",
    "threer-recycling.onrender.com",
]

# Apps
INSTALLED_APPS = [
    'daphne',  # <--- AÑADIDO: Servidor ASGI para Channels, debe ir primero.
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "ternium",
    "storages",  # AWS S3
    'channels',
    'chat.apps.ChatConfig', # <--- CORREGIDO: Usar la configuración de la app explícitamente
    'compras',
    "widget_tweaks",
    'cuentas_por_pagar',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware", # <--- AÑADIDO: Para servir archivos estáticos en producción.
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "r3_recycling.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# =================== CONFIGURACIÓN DE CHANNELS CORREGIDA ===================
# La aplicación ASGI principal está en tu proyecto 'r3_recycling', no en 'ternium'.
ASGI_APPLICATION = 'r3_recycling.asgi.application'

# Usa la variable de entorno de Render para Redis.
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [REDIS_URL],
        },
    },
}
# =========================================================================

WSGI_APPLICATION = "r3_recycling.wsgi.application"

# Base de datos (sin cambios, tu lógica original está bien)
if os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(
            default=os.environ["DATABASE_URL"],
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Validación de contraseñas (sin cambios)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internacionalización (sin cambios)
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I1N = True
USE_TZ = True

# AWS S3 Configuración (sin cambios, tu lógica original está bien)
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME")
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = "virtual"

AWS_STATIC_LOCATION = "static"
AWS_MEDIA_LOCATION = "media"

if AWS_STORAGE_BUCKET_NAME:
    AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com"
    STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_STATIC_LOCATION}/"
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/"
    STATICFILES_STORAGE = "storages.backends.s3boto3.S3StaticStorage"
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
else:
    STATIC_URL = "/static/"
    MEDIA_URL = "/media/"
    STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
    MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Esta línea es importante para que Render sepa dónde encontrar los archivos estáticos
# después de ejecutar 'collectstatic'.
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")


# Login / Logout (sin cambios)
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

# AutoField (sin cambios)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


CSRF_TRUSTED_ORIGINS = [
    "https://threer-recycling.onrender.com",
]