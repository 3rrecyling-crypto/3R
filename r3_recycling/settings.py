# r3_recycling/settings.py

from pathlib import Path
import os
import dj_database_url

# Base
BASE_DIR = Path(__file__).resolve().parent.parent

X_FRAME_OPTIONS = 'SAMEORIGIN'

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
    "app.3recycling.com.mx",          # <--- Agrega esta línea
    "www.3recycling.com.mx",
    "3recycling.com.mx",
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
    'facturacion',
    'flujo_bancos',
    'herramientas',
    'cargas_diesel',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'RH',
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware", # <--- AÑADIDO: Para servir archivos estáticos en producción.
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    'ternium.middleware.ProfileCompletionMiddleware',
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
LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Monterrey"
USE_I1N = True
USE_TZ = True

# AWS S3 Configuración (sin cambios, tu lógica original está bien)
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = "3rrecycling"
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME")
AWS_S3_SIGNATURE_VERSION = "s3v4"
AWS_S3_ADDRESSING_STYLE = "virtual"

# =========================================================================
# NUEVO: Forzar visualización de PDFs e imágenes en el navegador (inline)
# =========================================================================
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
    'ContentDisposition': 'inline',
}
# =========================================================================

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
    "https://www.3recycling.com.mx",
    "https://3recycling.com.mx",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://192.168.10.226:8000",
    "http://localhost:3000", # <--- AÑADIDO: Para permitir POST desde Next.js
    "http://127.0.0.1:3000", # <--- AÑADIDO
    "https://app.3recycling.com.mx",
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://app.3recycling.com.mx",
]

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER') 
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = 'Soporte 3R Recycling <3rrecycling@gmail.com>'

# TIEMPO DE SESIÓN (Para "Recordar sesión")
SESSION_COOKIE_AGE = 43200  # La sesión durará 12 horas (en segundos)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False # No cierra la sesión si cierra el navegador por error
BANXICO_API_TOKEN = os.environ.get('BANXICO_API_TOKEN')


# settings.py

# Credenciales de Twilio
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_FROM = 'whatsapp:+15707125385'           # Número Sandbox o tu número verificado
TWILIO_WHATSAPP_TO_APPROVER = 'whatsapp:+5218123465830'  # El número del jefe/aprobador
TWILIO_CONTENT_SID = os.getenv('TWILIO_CONTENT_SID')


# ──────────────────────────────────────────────────────────────
# DJANGO REST FRAMEWORK
# ──────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'api.pagination.DynamicPagePagination',
    'PAGE_SIZE': 25,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',  # útil en desarrollo
    ],
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S',
    'DATE_FORMAT': '%Y-%m-%d',
    'NON_FIELD_ERRORS_KEY': 'detail',
}

FISCALAPI_KEY = 'sk_test_332d6810_cbbc_45e1_aa05_c1d4b0cad058'
# URL base de pruebas (Revisa la documentación de tu proveedor para confirmar esta URL)
FISCALAPI_URL = 'https://test.fiscalapi.com/api/v4'
DOMAIN_URL = "https://3recycling.com.mx/"
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000


EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER') 
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = 'Soporte 3R Recycling <3rrecycling@gmail.com>'
CORS_ALLOW_CREDENTIALS = True # <--- ¡Te faltaba esta línea!

if not DEBUG:
    # --- CONFIGURACIÓN PARA PRODUCCIÓN (RENDER/DOMINIO REAL) ---
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_DOMAIN = ".3recycling.com.mx"
    # IMPORTANTE: el CSRF cookie debe vivir en el mismo dominio padre que
    # la cookie de sesión. Si no, app.3recycling.com.mx no puede leerla
    # y los POST/PUT/DELETE fallan con 403 "CSRF Failed" — sobre todo en
    # /diesel/api/login/ cuando queda una cookie de sesión expirada del
    # lado del navegador.
    CSRF_COOKIE_DOMAIN = ".3recycling.com.mx"
else:
    # --- CONFIGURACIÓN PARA DESARROLLO LOCAL (127.0.0.1) ---
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    # En local, Django usará el dominio y SameSite por defecto, permitiendo el login.