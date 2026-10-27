from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),

    path('cuentas/', include('cuentas.urls')),
    path('restaurantes/', include('restaurantes.urls')),
    path('productos/', include('catalogo.urls')),
    path('inventario/', include('inventario.urls')),
    path('recetas/', include('recetas.urls')),
    path('operativo/', include('operativo.urls')),
    path('caja/', include('caja.urls')),
    path('cocina/', include('cocina.urls')),
    path('menu/', include('menu_cliente.urls')),
    path('cliente/', include('cliente.urls')),
    path('', include('reportes.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
