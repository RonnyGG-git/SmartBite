import os
import secrets
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(ruta):
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding='utf-8').splitlines():
        linea = linea.strip()
        if linea and not linea.startswith('#') and '=' in linea:
            clave, valor = linea.split('=', 1)
            os.environ.setdefault(clave.strip(), valor.strip())


_cargar_env(BASE_DIR / '.env')


DEBUG = os.environ.get('DEBUG', 'False') == 'True'

_secret_key = os.environ.get('DJANGO_SECRET_KEY') or os.environ.get('SECRET_KEY')
if not _secret_key:
    if not DEBUG:
        raise ImproperlyConfigured(
            "Falta la variable de entorno SECRET_KEY (o DJANGO_SECRET_KEY). "
            'Genera una con: python -c "import secrets; print(secrets.token_urlsafe(50))"'
        )
    _secret_key = secrets.token_urlsafe(50)
SECRET_KEY = _secret_key

ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]

_render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f'https://{_render_host}')

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',

    'core',
    'cuentas',
    'restaurantes',
    'catalogo',
    'inventario',
    'recetas',
    'operativo',
    'caja',
    'cocina',
    'menu_cliente',
    'cliente',
    'reportes',
    'api',
    'asistente_cocina',
    'agente_telefonico',
]

AUTH_USER_MODEL = 'cuentas.Usuario'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'smartbite.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.restaurante',
            ],
        },
    },
]

WSGI_APPLICATION = 'smartbite.wsgi.application'


DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
    )
}


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'es'

TIME_ZONE = 'America/Bogota'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'cuentas:login'
LOGIN_REDIRECT_URL = 'reportes:dashboard'
LOGOUT_REDIRECT_URL = 'cuentas:login'

BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Smart Bite <no-reply@smartbite.local>')
EMAIL_BACKEND = (
    'core.correo.BrevoBackend' if BREVO_API_KEY else 'django.core.mail.backends.console.EmailBackend'
)

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': ['api.permisos.TieneRol'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'api.excepciones.manejador_de_errores',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Smart Bite API',
    'DESCRIPTION': 'API REST de Smart Bite. Autenticación: POST /api/v1/auth/token/ y luego '
                   'el encabezado "Authorization: Token <token>". Errores: {"detail", "code"}.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'estandar': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'consola': {
            'class': 'logging.StreamHandler',
            'formatter': 'estandar',
        },
    },
    'root': {
        'handlers': ['consola'],
        'level': 'ERROR',
    },
    'loggers': {
        'django.request': {
            'handlers': ['consola'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['consola'],
            'level': 'ERROR',
            'propagate': False,
        },
        'agente_telefonico': {
            'handlers': ['consola'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

AGENTE_MAX_SILENCIOS = int(os.environ.get('AGENTE_MAX_SILENCIOS', '3'))
AGENTE_MAX_TURNOS = int(os.environ.get('AGENTE_MAX_TURNOS', '60'))
AGENTE_VALIDAR_STOCK = os.environ.get('AGENTE_VALIDAR_STOCK', 'true').lower() == 'true'
AGENTE_RETENCION_DIAS = int(os.environ.get('AGENTE_RETENCION_DIAS', '30'))
