"""API de transferencias (links de descarga de 24 h).

Privado (empleados autenticados): crear, listar y eliminar sus transferencias.
Público (sin cuenta): consultar metadatos y descargar CADA archivo vía token.
El storage (disco o S3) jamás se expone: el backend hace de proxy y valida
token + expiración en cada request. Throttling anónimo global aplica (60/min).
"""
from __future__ import annotations

import re

from django.db.models import F
from django.http import FileResponse, JsonResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import ArchivoTransferencia, Transferencia
from .serializers import TransferenciaSerializer

MAX_ARCHIVOS = 60
MAX_ARCHIVO_MB = 300
MAX_TOTAL_MB = 1024


def _purgar_expiradas() -> None:
    """Borra blobs y registros de transferencias vencidas (limpieza perezosa)."""
    for t in Transferencia.objects.filter(expira_en__lt=timezone.now()):
        t.borrar_blobs()
        t.delete()


def _nombre_seguro(nombre: str) -> str:
    """Sanitiza el filename para el Content-Disposition (sin rutas ni control)."""
    limpio = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", "_", nombre).strip() or "archivo"
    return limpio[:150]


class TransferenciaViewSet(viewsets.ModelViewSet):
    serializer_class = TransferenciaSerializer
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return Transferencia.objects.filter(creado_por=self.request.user).prefetch_related("archivos")

    def list(self, request, *args, **kwargs):
        _purgar_expiradas()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        _purgar_expiradas()
        archivos = request.FILES.getlist("archivos")
        if not archivos:
            return Response({"detail": "Adjunta al menos un archivo (campo 'archivos')."}, status=400)
        if len(archivos) > MAX_ARCHIVOS:
            return Response({"detail": f"Máximo {MAX_ARCHIVOS} archivos por link."}, status=400)
        total = sum(f.size for f in archivos)
        if total > MAX_TOTAL_MB * 1024 * 1024:
            return Response({"detail": f"El paquete supera el máximo de {MAX_TOTAL_MB} MB."}, status=400)
        for f in archivos:
            if f.size > MAX_ARCHIVO_MB * 1024 * 1024:
                return Response({"detail": f"'{f.name}' supera el máximo de {MAX_ARCHIVO_MB} MB por archivo."}, status=400)

        t = Transferencia.objects.create(
            creado_por=request.user,
            titulo=(request.data.get("titulo") or "").strip()[:140],
        )
        try:
            for f in archivos:
                ArchivoTransferencia.objects.create(
                    transferencia=t, archivo=f, nombre=f.name[:255], tamano=f.size
                )
        except Exception:
            t.borrar_blobs()
            t.delete()
            return Response({"detail": "No se pudieron guardar los archivos."}, status=500)
        return Response(TransferenciaSerializer(t).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Transferencia):
        instance.borrar_blobs()
        instance.delete()


# ── Endpoints PÚBLICOS (sin cuenta) ──────────────────────────────────────────

def _obtener_valida(token: str) -> Transferencia | None:
    try:
        return Transferencia.objects.prefetch_related("archivos").get(token=token)
    except Transferencia.DoesNotExist:
        return None


@api_view(["GET"])
@permission_classes([AllowAny])
def publico_detalle(request, token: str):
    t = _obtener_valida(token)
    if not t:
        return Response({"detail": "Este link no existe o fue eliminado."}, status=404)
    if t.expirada:
        t.borrar_blobs()
        t.delete()
        return Response({"detail": "Este link expiró (validez de 24 horas)."}, status=410)
    return Response({
        "titulo": t.titulo,
        "creado_en": t.creado_en,
        "expira_en": t.expira_en,
        "archivos": [{"id": a.id, "nombre": a.nombre, "tamano": a.tamano} for a in t.archivos.all()],
        "total": sum(a.tamano for a in t.archivos.all()),
    })


def publico_descarga(request, token: str, archivo_id: int):
    """Descarga proxy: valida y sirve el blob SIN exponer el storage."""
    t = _obtener_valida(token)
    if not t:
        return JsonResponse({"detail": "Este link no existe o fue eliminado."}, status=404)
    if t.expirada:
        t.borrar_blobs()
        t.delete()
        return JsonResponse({"detail": "Este link expiró (validez de 24 horas)."}, status=410)
    a = t.archivos.filter(pk=archivo_id).first()
    if not a:
        return JsonResponse({"detail": "Archivo no encontrado."}, status=404)
    try:
        f = a.archivo.open("rb")
    except Exception:
        return JsonResponse({"detail": "El archivo ya no está disponible."}, status=410)
    Transferencia.objects.filter(pk=t.pk).update(descargas=F("descargas") + 1)
    resp = FileResponse(f, as_attachment=True, filename=_nombre_seguro(a.nombre))
    resp["X-Content-Type-Options"] = "nosniff"
    return resp
