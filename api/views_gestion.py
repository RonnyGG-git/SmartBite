from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import ProtectedError, Sum
from django.forms.models import model_to_dict
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from caja.models import Pago
from caja.vistas_qr import _qr_base64
from catalogo.forms import CategoriaForm, ProductoForm
from catalogo.imagenes import procesar_imagen
from catalogo.models import Categoria, ImagenProducto, Producto
from catalogo.views import ROLES_GESTION as ROLES_CATALOGO, ROLES_LECTURA as ROLES_CATALOGO_LECTURA
from cliente.models import Retroalimentacion
from cuentas.forms import UsuarioCreateForm, UsuarioForm, roles_de_empleado
from cuentas.models import Usuario
from cuentas.views import usuarios_del_restaurante
from core.tenancy import filtrar, limitar_opciones, restaurante_actual, restaurantes_accesibles
from inventario.forms import AjusteStockForm, ItemInventarioForm, ProveedorForm
from inventario.models import UNIDADES_MEDIDA, Compra, DetalleCompra, ItemInventario, MovimientoInventario, Proveedor
from inventario.servicios import anular_compra, recibir_compra
from inventario.views import ROLES_INVENTARIO, ROLES_LECTURA as ROLES_INVENTARIO_LECTURA
from operativo.forms import MesaForm
from operativo.models import Mesa, Orden
from recetas.forms import ProductoIngredienteForm
from recetas.models import ProductoIngrediente
from reportes.pdf import generar_pdf
from reportes.servicios import PeriodoInvalido, datos_reporte, leer_periodo, nombre_archivo
from recetas.views import ROLES_GESTION as ROLES_RECETAS, ROLES_LECTURA as ROLES_RECETAS_LECTURA
from restaurantes.forms import RestauranteForm, SucursalForm
from restaurantes.models import Restaurante, Sucursal

from .base import ConRestauranteMixin
from .serializers_gestion import (
    CategoriaGestionSerializer,
    CompraSerializer,
    ItemSerializer,
    MesaGestionSerializer,
    MovimientoSerializer,
    NuevaCompraSerializer,
    OpinionSerializer,
    ProductoGestionSerializer,
    ProveedorSerializer,
    RecetaSerializer,
    RestauranteGestionSerializer,
    RolSerializer,
    SucursalGestionSerializer,
    UsuarioGestionSerializer,
)
from .views_cuenta import errores_de_form

ROLES_ADMIN = ["ADMINISTRADOR"]
ROLES_MESAS_LECTURA = ["ADMINISTRADOR", "MESERO"]


def _datos(request):
    datos = request.data
    return datos.dict() if hasattr(datos, "dict") else dict(datos)


class CrudConFormulario(ConRestauranteMixin, viewsets.ModelViewSet):
    form_class = None
    form_edicion = None
    ruta_restaurante = None
    asignar_restaurante = False
    roles_lectura = ROLES_ADMIN
    roles_gestion = ROLES_ADMIN
    pagination_class = None

    @property
    def roles_permitidos(self):
        return self.roles_lectura if self.action in ("list", "retrieve") else self.roles_gestion

    def base(self):
        return self.queryset.all()

    def get_queryset(self):
        qs = self.base()
        return filtrar(qs, self.request, self.ruta_restaurante) if self.ruta_restaurante else qs

    def preparar(self, form):
        return limitar_opciones(form, self.request)

    def formulario(self, instancia=None):
        clase = self.form_edicion if instancia is not None and self.form_edicion else self.form_class
        datos = model_to_dict(instancia, fields=list(clase.base_fields)) if instancia is not None else {}
        datos = {clave: valor for clave, valor in datos.items() if valor is not None}
        datos.update(_datos(self.request))
        form = self.preparar(clase(data=datos, instance=instancia))
        if self.asignar_restaurante and form.instance.restaurante_id is None:
            form.instance.restaurante = restaurante_actual(self.request)
        return form

    def guardar(self, form, creando):
        return form.save()

    def responder(self, objeto, codigo):
        objeto = self.get_queryset().get(pk=objeto.pk)
        return Response(self.get_serializer(objeto).data, status=codigo)

    def create(self, request, *args, **kwargs):
        form = self.formulario()
        if self.asignar_restaurante and form.instance.restaurante_id is None:
            raise ValidationError("Primero registra un restaurante.", code="sin_restaurante")
        if not form.is_valid():
            raise errores_de_form(form)
        return self.responder(self.guardar(form, True), status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        form = self.formulario(self.get_object())
        if not form.is_valid():
            raise errores_de_form(form)
        return self.responder(self.guardar(form, False), status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        try:
            self.get_object().delete()
        except ProtectedError:
            raise ValidationError("No se puede eliminar: tiene registros que dependen de él.", code="en_uso")
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["gestion"])
class ItemGestionViewSet(CrudConFormulario):
    queryset = ItemInventario.objects.select_related("sucursal")
    serializer_class = ItemSerializer
    form_class = ItemInventarioForm
    ruta_restaurante = "sucursal__restaurante"
    roles_lectura = ROLES_INVENTARIO_LECTURA
    roles_gestion = ROLES_INVENTARIO

    @action(detail=True, methods=["post"])
    def ajustar(self, request, pk=None):
        item = self.get_object()
        form = AjusteStockForm(data=_datos(request))
        if not form.is_valid():
            raise errores_de_form(form)
        datos = form.cleaned_data
        item.ajustar_stock(datos["tipo"], datos["cantidad"], datos["motivo"])
        return self.responder(item, status.HTTP_200_OK)


@extend_schema(tags=["gestion"])
class ProveedorGestionViewSet(CrudConFormulario):
    queryset = Proveedor.objects.all()
    serializer_class = ProveedorSerializer
    form_class = ProveedorForm
    ruta_restaurante = "restaurante"
    asignar_restaurante = True
    roles_lectura = ROLES_INVENTARIO
    roles_gestion = ROLES_INVENTARIO


@extend_schema(tags=["gestion"])
class RecetaGestionViewSet(CrudConFormulario):
    queryset = ProductoIngrediente.objects.select_related("producto", "item_inventario")
    serializer_class = RecetaSerializer
    form_class = ProductoIngredienteForm
    ruta_restaurante = "producto__sucursal__restaurante"
    roles_lectura = ROLES_RECETAS_LECTURA
    roles_gestion = ROLES_RECETAS


@extend_schema(tags=["gestion"])
class CategoriaGestionViewSet(CrudConFormulario):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaGestionSerializer
    form_class = CategoriaForm
    ruta_restaurante = "restaurante"
    asignar_restaurante = True
    roles_lectura = ROLES_CATALOGO_LECTURA
    roles_gestion = ROLES_CATALOGO


@extend_schema(tags=["gestion"])
class ProductoGestionViewSet(CrudConFormulario):
    queryset = Producto.objects.select_related("categoria", "sucursal")
    serializer_class = ProductoGestionSerializer
    form_class = ProductoForm
    ruta_restaurante = "sucursal__restaurante"
    roles_lectura = ROLES_CATALOGO_LECTURA
    roles_gestion = ROLES_CATALOGO
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @action(detail=True, methods=["post"])
    def disponibilidad(self, request, pk=None):
        producto = self.get_object()
        producto.disponible = not producto.disponible
        producto.save(update_fields=["disponible", "actualizado_en"])
        return self.responder(producto, status.HTTP_200_OK)

    @action(detail=True, methods=["post", "delete"])
    def foto(self, request, pk=None):
        producto = self.get_object()
        with transaction.atomic():
            if request.method == "DELETE":
                ImagenProducto.objects.filter(producto=producto).delete()
                producto.imagen_version = 0
            else:
                archivo = request.FILES.get("archivo")
                if archivo is None:
                    raise ValidationError({"archivo": ["Elige una foto."]})
                try:
                    datos = procesar_imagen(archivo)
                except DjangoValidationError as error:
                    raise ValidationError({"archivo": error.messages})
                ImagenProducto.objects.update_or_create(producto=producto, defaults={"datos": datos})
                producto.url_imagen = ""
                producto.imagen_version = int(timezone.now().timestamp())
            producto.save(update_fields=["url_imagen", "imagen_version", "actualizado_en"])
        return self.responder(producto, status.HTTP_200_OK)


@extend_schema(tags=["gestion"])
class MesaGestionViewSet(CrudConFormulario):
    queryset = Mesa.objects.select_related("sucursal")
    serializer_class = MesaGestionSerializer
    form_class = MesaForm
    ruta_restaurante = "sucursal__restaurante"
    roles_lectura = ROLES_MESAS_LECTURA
    roles_gestion = ROLES_ADMIN

    @property
    def roles_permitidos(self):
        return self.roles_lectura if self.action in ("list", "retrieve", "qr") else self.roles_gestion

    @action(detail=True, methods=["get"])
    def qr(self, request, pk=None):
        mesa = self.get_object()
        url = request.build_absolute_uri(reverse("cliente:mesa", args=[mesa.pk]))
        return Response({"url": url, "qr_png_base64": _qr_base64(url), "numero": mesa.numero})


@extend_schema(tags=["gestion"])
class SucursalGestionViewSet(CrudConFormulario):
    queryset = Sucursal.objects.select_related("restaurante")
    serializer_class = SucursalGestionSerializer
    form_class = SucursalForm
    ruta_restaurante = "restaurante"


@extend_schema(tags=["gestion"])
class RestauranteGestionViewSet(CrudConFormulario):
    serializer_class = RestauranteGestionSerializer
    form_class = RestauranteForm

    def get_queryset(self):
        return restaurantes_accesibles(self.request.user).order_by("nombre")

    def preparar(self, form):
        return form

    def guardar(self, form, creando):
        if creando:
            form.instance.administrador = self.request.user
        return form.save()

    @action(detail=True, methods=["post"])
    def codigo(self, request, pk=None):
        restaurante = self.get_object()
        restaurante.regenerar_codigo_acceso()
        return self.responder(restaurante, status.HTTP_200_OK)


@extend_schema(tags=["gestion"])
class UsuarioGestionViewSet(CrudConFormulario):
    serializer_class = UsuarioGestionSerializer
    form_class = UsuarioCreateForm
    form_edicion = UsuarioForm

    def get_queryset(self):
        return usuarios_del_restaurante(self.request, Usuario.objects.select_related("rol", "sucursal")).order_by("nombre")

    def preparar(self, form):
        form = limitar_opciones(form, self.request)
        if not self.request.user.is_superuser:
            form.fields["rol"].queryset = roles_de_empleado()
        return form

    def guardar(self, form, creando):
        if creando and form.instance.restaurante_id is None:
            form.instance.restaurante = restaurante_actual(self.request)
        return form.save()

    def destroy(self, request, *args, **kwargs):
        if self.get_object().pk == request.user.pk:
            raise ValidationError("No puedes eliminar tu propia cuenta.", code="propia_cuenta")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def activo(self, request, pk=None):
        usuario = self.get_object()
        if usuario.pk == request.user.pk:
            raise ValidationError("No puedes desactivar tu propia cuenta.", code="propia_cuenta")
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=["is_active"])
        return self.responder(usuario, status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def roles(self, request):
        return Response(RolSerializer(roles_de_empleado(), many=True).data)


@extend_schema(tags=["gestion"])
class MovimientoGestionViewSet(ConRestauranteMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = MovimientoSerializer
    roles_permitidos = ROLES_INVENTARIO

    def get_queryset(self):
        return filtrar(MovimientoInventario.objects.select_related("item"), self.request, "item__sucursal__restaurante")


@extend_schema(tags=["gestion"])
class CompraGestionViewSet(ConRestauranteMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = CompraSerializer
    roles_permitidos = ROLES_INVENTARIO

    def get_queryset(self):
        return filtrar(
            Compra.objects.select_related("proveedor").prefetch_related("detalles__item"),
            self.request, "proveedor__restaurante",
        )

    @extend_schema(request=NuevaCompraSerializer, responses={201: CompraSerializer})
    def create(self, request):
        entrada = NuevaCompraSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        proveedor = filtrar(Proveedor.objects, request, "restaurante").filter(pk=datos["proveedor"]).first()
        if proveedor is None:
            raise ValidationError({"proveedor": ["Elige un proveedor de tu restaurante."]})
        items = filtrar(ItemInventario.objects, request, "sucursal__restaurante")
        with transaction.atomic():
            compra = Compra.objects.create(proveedor=proveedor)
            for linea in datos["detalles"]:
                item = items.filter(pk=linea["item"]).first()
                if item is None:
                    raise ValidationError({"detalles": ["Uno de los ítems no es de tu restaurante."]})
                DetalleCompra.objects.create(
                    compra=compra, item=item, cantidad=linea["cantidad"], costo_unitario=linea["costo_unitario"],
                )
        return Response(CompraSerializer(self.get_queryset().get(pk=compra.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def recibir(self, request, pk=None):
        compra = self.get_object()
        if not recibir_compra(compra):
            raise ValidationError("Solo se recibe una compra pendiente.", code="compra_no_pendiente")
        return Response(CompraSerializer(self.get_queryset().get(pk=compra.pk)).data)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        compra = self.get_object()
        if not anular_compra(compra):
            raise ValidationError("Solo se anula una compra pendiente.", code="compra_no_pendiente")
        return Response(CompraSerializer(self.get_queryset().get(pk=compra.pk)).data)


@extend_schema(tags=["gestion"])
class OpinionGestionViewSet(ConRestauranteMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = OpinionSerializer
    roles_permitidos = ROLES_ADMIN

    def get_queryset(self):
        return filtrar(Retroalimentacion.objects.select_related("mesa"), self.request, "mesa__sucursal__restaurante")

    @action(detail=True, methods=["post"])
    def revisar(self, request, pk=None):
        opinion = self.get_object()
        opinion.revisada = not opinion.revisada
        opinion.save(update_fields=["revisada", "actualizado_en"])
        return Response(OpinionSerializer(opinion).data)


@extend_schema(tags=["gestion"])
class DashboardView(ConRestauranteMixin, APIView):
    roles_permitidos = ROLES_ADMIN

    def get(self, request):
        hoy = timezone.localdate()
        mesas = filtrar(Mesa.objects, request, "sucursal__restaurante")
        ordenes = filtrar(Orden.objects, request, "sucursal__restaurante")
        pagos = filtrar(Pago.objects, request, "orden__sucursal__restaurante").filter(estado=Pago.APROBADO)
        items = filtrar(ItemInventario.objects, request, "sucursal__restaurante")
        actual = restaurante_actual(request)
        return Response({
            "restaurante": actual.nombre if actual else None,
            "total_usuarios": usuarios_del_restaurante(request).filter(is_active=True).count(),
            "total_productos": filtrar(Producto.objects, request, "sucursal__restaurante").count(),
            "total_mesas": mesas.count(),
            "mesas_ocupadas": mesas.filter(estado=Mesa.OCUPADA).count(),
            "ordenes_hoy": ordenes.filter(creado_en__date=hoy).count(),
            "ventas_hoy": str(pagos.filter(creado_en__date=hoy).aggregate(total=Sum("monto"))["total"] or 0),
            "stock_bajo": [{"id": i.pk, "nombre": i.nombre, "stock": i.stock_actual, "minimo": i.stock_minimo} for i in items if i.stock_bajo],
            "ordenes_por_estado": [
                {"estado": estado, "nombre": nombre, "cantidad": ordenes.filter(estado=estado).count()}
                for estado, nombre in Orden.ESTADO_CHOICES
            ],
            "ventas_por_metodo": [
                {"metodo": fila["metodo_pago__nombre"], "total": str(fila["total"])}
                for fila in pagos.values("metodo_pago__nombre").annotate(total=Sum("monto")).order_by("-total")
            ],
        })


@extend_schema(
    tags=["gestion"],
    parameters=[OpenApiParameter("desde", str, required=False), OpenApiParameter("hasta", str, required=False)],
    responses={(200, "application/pdf"): bytes},
)
class ReportePdfView(ConRestauranteMixin, APIView):
    roles_permitidos = ROLES_ADMIN

    def get(self, request):
        try:
            desde, hasta = leer_periodo(request.query_params.get("desde"), request.query_params.get("hasta"))
        except PeriodoInvalido as error:
            raise ValidationError({"detail": str(error)}, code="periodo_invalido")
        respuesta = HttpResponse(generar_pdf(datos_reporte(request, desde, hasta)), content_type="application/pdf")
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo(desde, hasta)}"'
        return respuesta


@extend_schema(tags=["gestion"])
class OpcionesView(APIView):
    def get(self, request):
        return Response({
            "unidades": [{"valor": valor, "etiqueta": etiqueta} for valor, etiqueta in UNIDADES_MEDIDA],
            "tipos_opinion": [{"valor": valor, "etiqueta": etiqueta} for valor, etiqueta in Retroalimentacion.TIPO_CHOICES],
        })
