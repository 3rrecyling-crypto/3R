from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

# Bitácora y módulos ERP (de SANBENITO) no existen en 3r: se neutralizan sin
# afectar el funcionamiento del editor de diagramas.
def log_evento(*args, **kwargs):
    return None


class _EmptyQS(list):
    def filter(self, *a, **k):
        return self

    def exclude(self, *a, **k):
        return self

    def values_list(self, *a, **k):
        return []

    def first(self):
        return None


class _Stub:
    objects = _EmptyQS()


AsignacionModulo = _Stub
Modulo = _Stub

from .models import Diagrama, DiagramaAprobacion, DiagramaCompartido, PlantillaCanvas
from .serializers import (
    AprobacionEventoSerializer,
    CompartidoSerializer,
    DiagramaListSerializer,
    DiagramaSerializer,
    PlantillaListSerializer,
    PlantillaSerializer,
)

User = get_user_model()

# Importar generar_imagen_ai de forma segura (opcional para no romper el módulo)
generar_imagen_ai = None
try:
    from .image_generator import generar_imagen_ai
except (ImportError, Exception):
    pass  # Si falla, generar_imagen_ai será None y el endpoint devolverá 503

# Generación de códigos QR / barras (opcional; si faltan libs, devuelve 503).
generar_codigo_svg = None
try:
    from .codigos import generar_codigo_svg
except (ImportError, Exception):
    pass

# Export a PDF (opcional; usa reportlab).
png_a_pdf_base64 = None
try:
    from .pdf_export import png_a_pdf_base64
except (ImportError, Exception):
    pass


class PlantillaCanvasViewSet(viewsets.ModelViewSet):
    """Plantillas del Canvas Pro.

    - Cada usuario ve: las GLOBALES (predeterminadas) + las SUYAS. Nada mas.
    - Solo staff/superuser crea/edita/borra las globales.
    - Cualquier usuario crea/edita/borra sus personales.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        u = self.request.user
        return PlantillaCanvas.objects.filter(
            Q(ambito=PlantillaCanvas.AMBITO_GLOBAL) | Q(creado_por=u)
        ).order_by("ambito", "orden", "-actualizado")

    def get_serializer_class(self):
        return PlantillaListSerializer if self.action == "list" else PlantillaSerializer

    def _es_admin(self) -> bool:
        u = self.request.user
        return bool(u.is_staff or u.is_superuser)

    def _puede_editar(self, obj: PlantillaCanvas) -> bool:
        if obj.ambito == PlantillaCanvas.AMBITO_GLOBAL:
            return self._es_admin()
        return obj.creado_por_id == self.request.user.id

    def perform_create(self, serializer):
        ambito = serializer.validated_data.get("ambito", PlantillaCanvas.AMBITO_PERSONAL)
        # Un usuario no-admin no puede crear predeterminadas globales.
        if ambito == PlantillaCanvas.AMBITO_GLOBAL and not self._es_admin():
            ambito = PlantillaCanvas.AMBITO_PERSONAL
        serializer.save(creado_por=self.request.user, ambito=ambito)

    def perform_update(self, serializer):
        obj = serializer.instance
        ambito = serializer.validated_data.get("ambito", obj.ambito)
        if ambito == PlantillaCanvas.AMBITO_GLOBAL and not self._es_admin():
            ambito = obj.ambito  # no permitir escalar a global
        serializer.save(ambito=ambito)

    def update(self, request, *args, **kwargs):
        if not self._puede_editar(self.get_object()):
            return Response(
                {"detail": "No tienes permiso para editar esta plantilla."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not self._puede_editar(self.get_object()):
            return Response(
                {"detail": "No tienes permiso para editar esta plantilla."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self._puede_editar(self.get_object()):
            return Response(
                {"detail": "No tienes permiso para eliminar esta plantilla."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)


class DiagramaViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        u = self.request.user
        qs = Diagrama.objects.select_related(
            # 3r: `modulo_vinculado` es IntegerField (no FK), NO va en select_related
            # o Django lanza FieldError y rompe todo el ViewSet.
            "creado_por", "aprobador", "decidido_por",
        ).prefetch_related(
            # Revive la rama optimizada de serializers._mi_permiso, que lee
            # exactamente este atributo (antes nunca se asignaba → N+1 real).
            Prefetch(
                "compartidos",
                queryset=DiagramaCompartido.objects.filter(usuario=u),
                to_attr="_prefetched_compartidos",
            ),
        )
        if u.is_superuser:
            return qs.order_by("-actualizado")
        # Visibilidad: propio + publico + compartido; el aprobador/decisor conserva la vista.
        qs = qs.filter(
            Q(creado_por=u)
            | Q(publico=True)
            | Q(compartidos__usuario=u)
            | Q(aprobador=u, estado=Diagrama.ESTADO_EN_REVISION)
            | Q(decidido_por=u)
        ).distinct()
        return qs.order_by("-actualizado")

    def get_serializer_class(self):
        if self.action == "list":
            return DiagramaListSerializer
        return DiagramaSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Marca "visto por el aprobador" la primera vez que el aprobador
        # designado abre un diagrama que espera su decision. Sirve para que el
        # creador sepa que su flujo ya fue revisado (aunque aun no decidido).
        if (
            instance.estado == Diagrama.ESTADO_EN_REVISION
            and instance.aprobador_id == request.user.id
            and instance.visto_por_aprobador_en is None
        ):
            instance.visto_por_aprobador_en = timezone.now()
            instance.save(update_fields=["visto_por_aprobador_en"])
            DiagramaAprobacion.objects.create(
                diagrama=instance, accion=DiagramaAprobacion.ACCION_VISTO,
                user=request.user,
            )
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        diagrama = serializer.save(creado_por=self.request.user)
        log_evento(
            user=self.request.user, accion="diagrama.crear",
            descripcion=f"Creo diagrama '{diagrama.titulo}'",
            meta={"diagrama_id": diagrama.id}, request=self.request,
        )

    def _puede_editar(self, diagrama: Diagrama) -> bool:
        u = self.request.user
        # Los aprobados+vinculados no se editan (solo desvinculando o creando version nueva).
        if diagrama.es_inmutable:
            return False
        if u.is_superuser or diagrama.creado_por_id == u.id:
            return True
        return DiagramaCompartido.objects.filter(
            diagrama=diagrama, usuario=u, permiso=DiagramaCompartido.PERMISO_EDITAR,
        ).exists()

    def _es_propietario(self, diagrama: Diagrama) -> bool:
        u = self.request.user
        return u.is_superuser or diagrama.creado_por_id == u.id

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.es_inmutable:
            return Response(
                {"detail": "Este diagrama esta aprobado y vinculado a un modulo. Desvinculalo primero para editarlo."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not self._puede_editar(instance):
            return Response(
                {"detail": "No tienes permiso para editar este diagrama."},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Si estaba RECHAZADO y se edita, vuelve a BORRADOR.
        if instance.estado == Diagrama.ESTADO_RECHAZADO:
            instance.estado = Diagrama.ESTADO_BORRADOR
            instance.save(update_fields=["estado"])
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.es_inmutable:
            return Response(
                {"detail": "Este diagrama esta aprobado y vinculado a un modulo. Desvinculalo primero para editarlo."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not self._puede_editar(instance):
            return Response(
                {"detail": "No tienes permiso para editar este diagrama."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if instance.estado == Diagrama.ESTADO_RECHAZADO:
            instance.estado = Diagrama.ESTADO_BORRADOR
            instance.save(update_fields=["estado"])
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.es_inmutable:
            return Response(
                {"detail": "No se puede eliminar: el diagrama esta aprobado y vinculado a un módulo. "
                           "Desvinculalo primero."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not self._es_propietario(instance):
            return Response(
                {"detail": "Solo el propietario puede eliminar el diagrama."},
                status=status.HTTP_403_FORBIDDEN,
            )
        log_evento(
            user=request.user, accion="diagrama.eliminar",
            descripcion=f"Elimino diagrama '{instance.titulo}'",
            meta={"diagrama_id": instance.id}, request=request,
        )
        return super().destroy(request, *args, **kwargs)

    # ── Aprobacion ────────────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], url_path="enviar-aprobacion")
    def enviar_aprobacion(self, request, pk=None):
        """Envia el diagrama a revision asignando un aprobador.

        Body: { "aprobador_id": <user_id>, "comentario": "..." }
        El propio creador puede listarse como aprobador (auto-aprobacion).
        """
        diagrama = self.get_object()
        if not self._puede_editar(diagrama):
            return Response({"detail": "Sin permiso para enviar a aprobacion."}, status=403)
        if diagrama.estado == Diagrama.ESTADO_EN_REVISION:
            return Response({"detail": "El diagrama ya esta en revision."}, status=400)
        if diagrama.estado == Diagrama.ESTADO_APROBADO:
            return Response({"detail": "El diagrama ya esta aprobado."}, status=400)

        aprobador_id = request.data.get("aprobador_id") or request.user.id
        aprobador = User.objects.filter(pk=aprobador_id).first()
        if not aprobador:
            return Response({"detail": "Aprobador no encontrado."}, status=404)
        # Solo el creador puede auto-aprobarse. Un editor invitado NO puede
        # designarse a sí mismo como aprobador (si no, aprobaría su propio cambio).
        if aprobador.id == request.user.id and diagrama.creado_por_id != request.user.id:
            return Response(
                {"detail": "Un editor no puede designarse a sí mismo como aprobador."},
                status=403,
            )
        comentario = (request.data.get("comentario") or "")[:600]

        diagrama.estado = Diagrama.ESTADO_EN_REVISION
        diagrama.aprobador = aprobador
        diagrama.enviado_aprobacion_en = timezone.now()
        diagrama.visto_por_aprobador_en = None
        diagrama.decidido_en = None
        diagrama.decidido_por = None
        diagrama.comentario_decision = ""
        diagrama.save(update_fields=[
            "estado", "aprobador", "enviado_aprobacion_en", "visto_por_aprobador_en",
            "decidido_en", "decidido_por", "comentario_decision",
        ])
        DiagramaAprobacion.objects.create(
            diagrama=diagrama, accion=DiagramaAprobacion.ACCION_ENVIO,
            user=request.user, aprobador_destinado=aprobador, comentario=comentario,
        )
        log_evento(
            user=request.user, accion="diagrama.enviar_aprobacion",
            descripcion=f"Envio '{diagrama.titulo}' a aprobacion de {aprobador.username}",
            meta={"diagrama_id": diagrama.id, "aprobador_id": aprobador.id},
            request=request,
        )
        return Response(DiagramaSerializer(diagrama, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="aprobar")
    def aprobar(self, request, pk=None):
        diagrama = self.get_object()
        u = request.user
        es_aprobador = diagrama.aprobador_id == u.id
        es_creador_self_approval = diagrama.creado_por_id == u.id and diagrama.aprobador_id == u.id
        if not (u.is_superuser or es_aprobador or es_creador_self_approval):
            return Response({"detail": "Solo el aprobador designado puede aprobar."}, status=403)
        if diagrama.estado != Diagrama.ESTADO_EN_REVISION:
            return Response({"detail": "El diagrama no esta en revision."}, status=400)

        comentario = (request.data.get("comentario") or "")[:600]
        diagrama.estado = Diagrama.ESTADO_APROBADO
        diagrama.decidido_en = timezone.now()
        diagrama.decidido_por = u
        diagrama.comentario_decision = comentario
        with transaction.atomic():
            diagrama.save(update_fields=["estado", "decidido_en", "decidido_por", "comentario_decision"])
            DiagramaAprobacion.objects.create(
                diagrama=diagrama, accion=DiagramaAprobacion.ACCION_APROBAR,
                user=u, comentario=comentario,
            )
        log_evento(
            user=u, accion="diagrama.aprobar",
            descripcion=f"Aprobo diagrama '{diagrama.titulo}'",
            meta={"diagrama_id": diagrama.id}, request=request,
        )
        return Response(DiagramaSerializer(diagrama, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="rechazar")
    def rechazar(self, request, pk=None):
        diagrama = self.get_object()
        u = request.user
        if not (u.is_superuser or diagrama.aprobador_id == u.id):
            return Response({"detail": "Solo el aprobador designado puede rechazar."}, status=403)
        if diagrama.estado != Diagrama.ESTADO_EN_REVISION:
            return Response({"detail": "El diagrama no esta en revision."}, status=400)

        comentario = (request.data.get("comentario") or "")[:600]
        diagrama.estado = Diagrama.ESTADO_RECHAZADO
        diagrama.decidido_en = timezone.now()
        diagrama.decidido_por = u
        diagrama.comentario_decision = comentario
        with transaction.atomic():
            diagrama.save(update_fields=["estado", "decidido_en", "decidido_por", "comentario_decision"])
            DiagramaAprobacion.objects.create(
                diagrama=diagrama, accion=DiagramaAprobacion.ACCION_RECHAZAR,
                user=u, comentario=comentario,
            )
        log_evento(
            user=u, accion="diagrama.rechazar", nivel="WARN",
            descripcion=f"Rechazo diagrama '{diagrama.titulo}': {comentario}",
            meta={"diagrama_id": diagrama.id}, request=request,
        )
        return Response(DiagramaSerializer(diagrama, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="vincular-modulo")
    def vincular_modulo(self, request, pk=None):
        """Vincula el diagrama a un modulo del ERP. Solo aprobados.

        Body: { "modulo_id": <id> | null }
        modulo_id=null -> desvincula.
        """
        # La vinculación de diagramas a módulos del ERP no aplica en este backend.
        return Response({"detail": "La vinculación a módulos no está disponible en este sistema."}, status=400)

    @action(detail=False, methods=["get"], url_path="por-modulo")
    def por_modulo(self, request):
        """Diagramas APROBADOS y vinculados que pertenecen a un modulo.

        Acepta `?codigo=<codigo_modulo>` (exacto) o `?ruta=<pathname>` (todos los
        modulos cuya `ruta_frontend` sea prefijo de la ruta actual, p.ej.
        /almacen cubre /almacen/productos). Respeta la visibilidad de
        get_queryset(): un usuario solo ve los diagramas de modulos a los que
        tiene acceso.
        """
        # La vinculación a módulos ERP no aplica en este backend: sin resultados.
        return Response({"count": 0, "results": []})

    @action(detail=False, methods=["get"], url_path="pendientes-aprobacion")
    def pendientes_aprobacion(self, request):
        """Diagramas que esperan MI aprobacion."""
        qs = Diagrama.objects.select_related("creado_por").filter(
            aprobador=request.user, estado=Diagrama.ESTADO_EN_REVISION,
        ).order_by("-enviado_aprobacion_en")
        return Response({
            "count": qs.count(),
            "results": DiagramaListSerializer(qs, many=True, context={"request": request}).data,
        })

    # ── Comparticiones ────────────────────────────────────────────────────────
    @action(detail=True, methods=["get", "post"], url_path="compartidos")
    def compartidos(self, request, pk=None):
        diagrama = self.get_object()
        if request.method == "GET":
            comps = diagrama.compartidos.select_related("usuario", "compartido_por")
            return Response(CompartidoSerializer(comps, many=True).data)

        if not self._es_propietario(diagrama):
            return Response(
                {"detail": "Solo el propietario puede compartir el diagrama."},
                status=status.HTTP_403_FORBIDDEN,
            )

        username = (request.data.get("username") or "").strip()
        user_id = request.data.get("user_id")
        permiso = request.data.get("permiso") or DiagramaCompartido.PERMISO_VER
        if permiso not in dict(DiagramaCompartido.PERMISO_CHOICES):
            return Response({"detail": "Permiso invalido."}, status=400)

        usuario = None
        if user_id:
            usuario = User.objects.filter(pk=user_id).first()
        elif username:
            usuario = User.objects.filter(username__iexact=username).first()
        if not usuario:
            return Response({"detail": "Usuario no encontrado."}, status=404)
        if usuario.id == diagrama.creado_por_id:
            return Response({"detail": "El propietario ya tiene acceso."}, status=400)

        comp, created = DiagramaCompartido.objects.update_or_create(
            diagrama=diagrama, usuario=usuario,
            defaults={"permiso": permiso, "compartido_por": request.user},
        )
        return Response(CompartidoSerializer(comp).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["patch", "delete"],
            url_path=r"compartidos/(?P<comp_id>\d+)")
    def compartido_detalle(self, request, pk=None, comp_id=None):
        diagrama = self.get_object()
        if not self._es_propietario(diagrama):
            return Response(
                {"detail": "Solo el propietario puede modificar el acceso."},
                status=status.HTTP_403_FORBIDDEN,
            )
        comp = DiagramaCompartido.objects.filter(pk=comp_id, diagrama=diagrama).first()
        if not comp:
            return Response({"detail": "Comparticion no encontrada."}, status=404)

        if request.method == "DELETE":
            comp.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        permiso = request.data.get("permiso")
        if permiso not in dict(DiagramaCompartido.PERMISO_CHOICES):
            return Response({"detail": "Permiso invalido."}, status=400)
        comp.permiso = permiso
        comp.save(update_fields=["permiso"])
        return Response(CompartidoSerializer(comp).data)

    @action(detail=True, methods=["post"], url_path="generar-imagen")
    def generar_imagen(self, request, pk=None):
        """
        Genera una imagen con IA (Gemini) e insertable en el canvas.
        Espera: { "prompt": "descripcion", "empresa": <id opcional> }
        Retorna: { "imagen_url": "data:image/png;base64,..." }
        """
        if generar_imagen_ai is None:
            return Response(
                {"detail": "La generación de imágenes no está disponible. Instala: pip install google-genai"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        diagrama = self.get_object()

        # Verificar permisos de edición
        if not self._puede_editar(diagrama):
            return Response(
                {"detail": "No tienes permiso para editar este diagrama."},
                status=status.HTTP_403_FORBIDDEN,
            )

        prompt = request.data.get("prompt", "").strip()
        if not prompt:
            return Response(
                {"detail": "El prompt no puede estar vacío."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(prompt) > 500:
            return Response(
                {"detail": "El prompt es muy largo (máx 500 caracteres)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Empresa para resolver la key de Gemini del panel (opcional).
        empresa_id = request.data.get("empresa")
        try:
            empresa_id = int(empresa_id) if empresa_id else None
        except (TypeError, ValueError):
            empresa_id = None

        # Semilla opcional para variaciones ("generar 4 opciones").
        seed = request.data.get("seed")
        try:
            seed = int(seed) if seed is not None and seed != "" else None
        except (TypeError, ValueError):
            seed = None

        try:
            imagen_data_url = generar_imagen_ai(prompt, empresa_id=empresa_id, seed=seed)
            return Response(
                {"imagen_url": imagen_data_url},
                status=status.HTTP_201_CREATED,
            )
        except ValueError as e:
            # Errores esperables (falta key, prompt bloqueado…): mensaje claro.
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {
                    "detail": f"Error generando imagen: {str(e)}",
                    "error_type": type(e).__name__,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], url_path="generar-codigo")
    def generar_codigo(self, request):
        """
        Genera un código QR o de barras como SVG (vectorial) para el canvas.
        Espera: { "tipo": "qr"|"barcode", "valor": "...", "formato": "code128" }
        Retorna: { "svg": "<svg…>", "w": <px>, "h": <px> }
        """
        if generar_codigo_svg is None:
            return Response(
                {"detail": "Generación de códigos no disponible. Instala: pip install qrcode python-barcode"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        tipo = (request.data.get("tipo") or "qr").strip().lower()
        valor = (request.data.get("valor") or "").strip()
        formato = (request.data.get("formato") or "code128").strip().lower()
        if not valor:
            return Response({"detail": "Escribe el valor del código (texto, URL, número…)."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            data = generar_codigo_svg(tipo, valor, formato)
            return Response(data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Error generando el código: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["post"], url_path="exportar-pdf")
    def exportar_pdf(self, request):
        """
        Convierte el lienzo (PNG que manda el frontend) en un PDF de una página.
        Espera: { "png": "data:image/png;base64,...", "w": <px>, "h": <px> }
        Retorna: { "pdf": "<base64>" }
        """
        if png_a_pdf_base64 is None:
            return Response(
                {"detail": "Export a PDF no disponible (falta reportlab)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        png = request.data.get("png") or ""
        if not png.startswith("data:image"):
            return Response({"detail": "No se recibió una imagen válida del lienzo."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            w = float(request.data.get("w") or 800)
            h = float(request.data.get("h") or 600)
        except (TypeError, ValueError):
            w, h = 800.0, 600.0
        try:
            pdf_b64 = png_a_pdf_base64(png, w, h)
            return Response({"pdf": pdf_b64}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": f"No se pudo generar el PDF: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ── Usuarios disponibles (para compartir diagramas / elegir aprobador) ────────
# SANBENITO exponía /api/core/usuarios/. En 3r no existe la app core, así que se
# ofrece aquí una lista mínima de usuarios activos accesible a cualquier usuario
# autenticado. Devuelve la forma { results: [...] } que espera el frontend.
class UsuariosDisponiblesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = User.objects.filter(is_active=True).order_by("username")
        results = [
            {
                "id": u.id,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "nombre": (u.get_full_name() or u.username),
                "email": u.email,
            }
            for u in qs
        ]
        return Response({"results": results, "count": len(results)})
