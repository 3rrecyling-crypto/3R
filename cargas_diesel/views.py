from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.shortcuts import render
from rest_framework.permissions import IsAuthenticated

from .models import (
    Patio, Totem, CargaDiesel, Unidad, CompraCombustible,
    AjusteInventario, ProveedorDiesel, PerfilUsuarioDiesel
)
from .serializers import (
    PatioSerializer, TotemSerializer, TotemConfigSerializer,
    CargaDieselSerializer, UnidadSerializer, UnidadRendimientoSerializer,
    CompraCombustibleSerializer, AjusteInventarioSerializer,
    ProveedorSerializer
)


def get_patios_usuario(user):
    """Retorna los patios a los que tiene acceso el usuario."""
    # 1. First, check if the user is actually logged in
    if not user.is_authenticated:
        return Patio.objects.none()

    try:
        perfil = user.perfil_diesel
        return perfil.get_patios_permitidos()
    except PerfilUsuarioDiesel.DoesNotExist:
        # Si no tiene perfil, y es superuser, ve todo
        if getattr(user, 'is_superuser', False):
            return Patio.objects.filter(activo=True)
        return Patio.objects.none()


# ─────────────────────────────────────────────
# PATIOS
# ─────────────────────────────────────────────
class PatiosListAPIView(generics.ListAPIView):
    serializer_class = PatioSerializer

    def get_queryset(self):
        return get_patios_usuario(self.request.user)


# ─────────────────────────────────────────────
# PROVEEDORES
# ─────────────────────────────────────────────
class ProveedoresListAPIView(generics.ListAPIView):
    queryset = ProveedorDiesel.objects.filter(activo=True)
    serializer_class = ProveedorSerializer


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
class DashboardAPIView(APIView):
    permission_classes = [IsAuthenticated] # <--- Prevents unauthenticated access

    def get(self, request):
        patio_id = request.query_params.get('patio')
        patios = get_patios_usuario(request.user)

        if patio_id:
            patios = patios.filter(id=patio_id)

        # Tótems de los patios
        totems_data = []
        for patio in patios:
            totem = getattr(patio, 'totem', None)
            if totem:
                totems_data.append(TotemSerializer(totem).data)

        # Consolidado global
        totem_global = None
        if len(totems_data) > 1:
            total_diesel = sum(float(t.get('cantidad_diesel', 0)) for t in totems_data)
            cap_diesel = sum(float(t.get('capacidad_diesel', 0)) for t in totems_data)
            total_urea = sum(float(t.get('cantidad_urea', 0)) for t in totems_data)
            cap_urea = sum(float(t.get('capacidad_urea', 0)) for t in totems_data)

            totem_global = {
                'cantidad_diesel': total_diesel,
                'capacidad_diesel': cap_diesel,
                'porcentaje_diesel': round((total_diesel / cap_diesel * 100), 1) if cap_diesel else 0,
                'cantidad_urea': total_urea,
                'capacidad_urea': cap_urea,
                'porcentaje_urea': round((total_urea / cap_urea * 100), 1) if cap_urea else 0,
                'estado_diesel': 'optimo' if cap_diesel and (total_diesel / cap_diesel) >= 0.7 else
                                 'moderado' if cap_diesel and (total_diesel / cap_diesel) >= 0.4 else
                                 'bajo' if cap_diesel and (total_diesel / cap_diesel) >= 0.15 else 'critico',
                'estado_urea': 'optimo' if cap_urea and (total_urea / cap_urea) >= 0.7 else
                               'moderado' if cap_urea and (total_urea / cap_urea) >= 0.4 else
                               'bajo' if cap_urea and (total_urea / cap_urea) >= 0.15 else 'critico',
            }

        # Estadísticas del mes
        inicio_mes = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        patio_ids = patios.values_list('id', flat=True)

        cargas_mes = CargaDiesel.objects.filter(
            patio_id__in=patio_ids, fecha_carga__gte=inicio_mes
        )
        stats_mes = cargas_mes.aggregate(
            total_cargas=Count('id'),
            litros_despachados=Sum('litros_diesel'),
            costo_total=Sum('costo_total'),
            rendimiento_promedio=Avg('rendimiento')
        )

        # Cargas recientes
        cargas_recientes = CargaDiesel.objects.filter(
            patio_id__in=patio_ids
        ).select_related('unidad', 'patio', 'usuario').order_by('-fecha_carga')[:15]

        return Response({
            'totems': totems_data,
            'totem_global': totem_global,
            'cargas_recientes': CargaDieselSerializer(cargas_recientes, many=True).data,
            'stats': {
                'total_cargas_mes': stats_mes['total_cargas'] or 0,
                'litros_despachados_mes': float(stats_mes['litros_despachados'] or 0),
                'costo_total_mes': float(stats_mes['costo_total'] or 0),
                'rendimiento_promedio': round(float(stats_mes['rendimiento_promedio'] or 0), 2),
            },
            'patios': PatioSerializer(patios, many=True).data,
            'ultima_actualizacion': timezone.now().isoformat(),
        })


# ─────────────────────────────────────────────
# UNIDADES
# ─────────────────────────────────────────────
class UnidadesListAPIView(generics.ListAPIView):
    serializer_class = UnidadSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['numero_economico', 'descripcion']

    def get_queryset(self):
        qs = Unidad.objects.filter(activo=True).select_related('patio')
        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)
        return qs


class UnidadesRendimientoListAPIView(generics.ListAPIView):
    """Lista de unidades con datos de rendimiento calculados."""
    serializer_class = UnidadRendimientoSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['numero_economico', 'descripcion']

    def get_queryset(self):
        patios = get_patios_usuario(self.request.user)
        qs = Unidad.objects.filter(
            activo=True, patio__in=patios
        ).select_related('patio').prefetch_related('cargas')

        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)
        return qs


# ─────────────────────────────────────────────
# CARGAS
# ─────────────────────────────────────────────
class CargaDieselListAPIView(generics.ListAPIView):
    serializer_class = CargaDieselSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['unidad__numero_economico']

    def get_queryset(self):
        patios = get_patios_usuario(self.request.user)
        qs = CargaDiesel.objects.filter(
            patio__in=patios
        ).select_related('unidad', 'patio', 'usuario')

        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)

        unidad = self.request.query_params.get('unidad')
        if unidad:
            qs = qs.filter(unidad__numero_economico__icontains=unidad)

        fecha_inicio = self.request.query_params.get('fecha_inicio')
        fecha_fin = self.request.query_params.get('fecha_fin')
        if fecha_inicio:
            qs = qs.filter(fecha_carga__date__gte=fecha_inicio)
        if fecha_fin:
            qs = qs.filter(fecha_carga__date__lte=fecha_fin)

        return qs


class CargaDieselCreateAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = CargaDieselSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(usuario=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────
# COMPRAS
# ─────────────────────────────────────────────
class CompraListAPIView(generics.ListAPIView):
    serializer_class = CompraCombustibleSerializer

    def get_queryset(self):
        patios = get_patios_usuario(self.request.user)
        qs = CompraCombustible.objects.filter(
            patio__in=patios
        ).select_related('proveedor', 'patio', 'usuario')

        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)
        return qs


class CompraCreateAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = CompraCombustibleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(usuario=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────
# AJUSTES DE INVENTARIO
# ─────────────────────────────────────────────
class AjusteListAPIView(generics.ListAPIView):
    serializer_class = AjusteInventarioSerializer

    def get_queryset(self):
        patios = get_patios_usuario(self.request.user)
        qs = AjusteInventario.objects.filter(
            patio__in=patios
        ).select_related('patio', 'usuario')

        patio_id = self.request.query_params.get('patio')
        if patio_id:
            qs = qs.filter(patio_id=patio_id)
        return qs


class AjusteCreateAPIView(APIView):
    def post(self, request):
        serializer = AjusteInventarioSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(usuario=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────
# CONFIGURACIÓN DEL TÓTEM
# ─────────────────────────────────────────────
class TotemConfigAPIView(APIView):
    def get(self, request, patio_id):
        try:
            patio = get_patios_usuario(request.user).get(id=patio_id)
            totem = patio.totem
            return Response(TotemSerializer(totem).data)
        except (Patio.DoesNotExist, Totem.DoesNotExist):
            return Response({"error": "Tótem no encontrado"}, status=404)

    def patch(self, request, patio_id):
        try:
            patio = get_patios_usuario(request.user).get(id=patio_id)
            totem = patio.totem
            serializer = TotemConfigSerializer(totem, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(TotemSerializer(totem).data)
            return Response(serializer.errors, status=400)
        except (Patio.DoesNotExist, Totem.DoesNotExist):
            return Response({"error": "Tótem no encontrado"}, status=404)


# ─────────────────────────────────────────────
# VISTAS DE PÁGINAS (TEMPLATES)
# ─────────────────────────────────────────────
def formulario_carga_view(request):
    """
    Vista encargada de renderizar la plantilla HTML del formulario de carga.
    """
    return render(request, 'cargas_diesel/formulario_carga.html')

# ─────────────────────────────────────────────
# VISTAS DE PÁGINAS (TEMPLATES)
# ─────────────────────────────────────────────
def dashboard_view(request):
    """
    Vista encargada de renderizar la plantilla HTML del dashboard de diésel.
    """
    return render(request, 'cargas_diesel/dashboard.html') 

def formulario_carga_view(request):
    """
    Vista encargada de renderizar la plantilla HTML del formulario de carga.
    """
    return render(request, 'cargas_diesel/formulario_carga.html')

from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

# Decorador vital para que Django le envíe el token CSRF a Next.js
@method_decorator(ensure_csrf_cookie, name='dispatch')
class LoginAPIView(APIView):
    permission_classes = [AllowAny] # Permite acceso a usuarios no logueados

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user) # Esto es lo que genera la cookie de sesión real
            return Response({
                "detail": "Login exitoso", 
                "username": user.username
            })
        else:
            return Response(
                {"detail": "Credenciales inválidas"}, 
                status=status.HTTP_401_UNAUTHORIZED
            )
