from rest_framework import serializers

from .models import Diagrama, DiagramaAprobacion, DiagramaCompartido, PlantillaCanvas


def _plantilla_puede_editar(p: "PlantillaCanvas", request) -> bool:
    u = getattr(request, "user", None)
    if not u or not u.is_authenticated:
        return False
    if p.ambito == PlantillaCanvas.AMBITO_GLOBAL:
        return bool(u.is_staff or u.is_superuser)
    return p.creado_por_id == u.id


class PlantillaListSerializer(serializers.ModelSerializer):
    """Version liviana (sin `data`) para la galeria."""
    puede_editar = serializers.SerializerMethodField()
    es_mia = serializers.SerializerMethodField()

    class Meta:
        model = PlantillaCanvas
        fields = ["id", "titulo", "descripcion", "categoria", "miniatura", "ambito",
                  "orden", "creado", "actualizado", "puede_editar", "es_mia"]
        read_only_fields = ["creado", "actualizado", "puede_editar", "es_mia"]

    def get_puede_editar(self, p) -> bool:
        return _plantilla_puede_editar(p, self.context.get("request"))

    def get_es_mia(self, p) -> bool:
        req = self.context.get("request")
        u = getattr(req, "user", None)
        return bool(u and u.is_authenticated and p.creado_por_id == u.id)


class PlantillaSerializer(serializers.ModelSerializer):
    """Version completa (con `data`) para crear/editar/abrir."""
    puede_editar = serializers.SerializerMethodField()
    es_mia = serializers.SerializerMethodField()

    class Meta:
        model = PlantillaCanvas
        fields = ["id", "titulo", "descripcion", "categoria", "data", "miniatura",
                  "ambito", "orden", "creado", "actualizado", "puede_editar", "es_mia"]
        read_only_fields = ["creado", "actualizado", "puede_editar", "es_mia"]

    def get_puede_editar(self, p) -> bool:
        return _plantilla_puede_editar(p, self.context.get("request"))

    def get_es_mia(self, p) -> bool:
        req = self.context.get("request")
        u = getattr(req, "user", None)
        return bool(u and u.is_authenticated and p.creado_por_id == u.id)


def _mi_permiso(d: Diagrama, request) -> str:
    """Permiso del usuario autenticado sobre el diagrama:
    - 'propietario' si es el creador (o superuser)
    - 'editar' si tiene una comparticion con permiso editar
    - 'ver' si solo es publico o comparticion ver
    """
    if not request or not request.user.is_authenticated:
        return "ver" if d.publico else "ninguno"
    u = request.user
    if u.is_superuser or d.creado_por_id == u.id:
        return "propietario"
    # Buscar entre comparticiones
    comp = next((c for c in getattr(d, "_prefetched_compartidos", []) if c.usuario_id == u.id), None)
    if comp is None:
        # Si no se prefetcho, hacer lookup directo (lista corta, no es caro)
        comp = DiagramaCompartido.objects.filter(diagrama=d, usuario=u).first()
    if comp:
        return comp.permiso  # "ver" o "editar"
    return "ver" if d.publico else "ninguno"


class DiagramaListSerializer(serializers.ModelSerializer):
    """Version liviana sin `data` para listados (la JSON puede ser grande)."""
    creado_por_username = serializers.CharField(source="creado_por.username", read_only=True, default="")
    nodos_count = serializers.SerializerMethodField()
    mi_permiso = serializers.SerializerMethodField()
    # Tipo de documento visual ("gantt", "canvas" o "" = flowchart). Permite que
    # cada modulo (p.ej. Canvas Pro) filtre sus propios items sin bajar `data`.
    tipo = serializers.SerializerMethodField()
    aprobador_username = serializers.CharField(source="aprobador.username", read_only=True, default="")
    decidido_por_username = serializers.CharField(source="decidido_por.username", read_only=True, default="")
    modulo_codigo = serializers.CharField(source="modulo_vinculado.codigo", read_only=True, default="")
    modulo_nombre = serializers.CharField(source="modulo_vinculado.nombre", read_only=True, default="")

    class Meta:
        model = Diagrama
        fields = ["id", "titulo", "descripcion", "publico", "miniatura",
                  "creado", "actualizado", "creado_por", "creado_por_username",
                  "nodos_count", "mi_permiso", "tipo",
                  "estado", "aprobador", "aprobador_username",
                  "enviado_aprobacion_en", "visto_por_aprobador_en", "decidido_en",
                  "decidido_por_username", "comentario_decision",
                  "modulo_vinculado", "modulo_codigo", "modulo_nombre"]
        read_only_fields = ["creado", "actualizado", "creado_por", "creado_por_username",
                            "mi_permiso", "estado", "aprobador", "aprobador_username",
                            "enviado_aprobacion_en", "visto_por_aprobador_en", "decidido_en",
                            "decidido_por_username", "comentario_decision",
                            "modulo_vinculado", "modulo_codigo", "modulo_nombre"]

    def get_nodos_count(self, d: Diagrama) -> int:
        try:
            return len((d.data or {}).get("nodes", []))
        except Exception:
            return 0

    def get_tipo(self, d: Diagrama) -> str:
        try:
            return str((d.data or {}).get("tipo") or "")
        except Exception:
            return ""

    def get_mi_permiso(self, d: Diagrama) -> str:
        return _mi_permiso(d, self.context.get("request"))


class CompartidoSerializer(serializers.ModelSerializer):
    usuario_username = serializers.CharField(source="usuario.username", read_only=True)
    usuario_nombre = serializers.SerializerMethodField()
    compartido_por_username = serializers.CharField(
        source="compartido_por.username", read_only=True, default="",
    )

    class Meta:
        model = DiagramaCompartido
        fields = ["id", "usuario", "usuario_username", "usuario_nombre",
                  "permiso", "compartido_por", "compartido_por_username", "creado"]
        read_only_fields = ["creado", "compartido_por", "compartido_por_username",
                            "usuario_username", "usuario_nombre"]

    def get_usuario_nombre(self, c: DiagramaCompartido) -> str:
        u = c.usuario
        full = f"{u.first_name} {u.last_name}".strip()
        return full or u.username


class AprobacionEventoSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source="user.username", read_only=True, default="")
    aprobador_destinado_username = serializers.CharField(
        source="aprobador_destinado.username", read_only=True, default="",
    )
    modulo_nombre = serializers.CharField(source="modulo.nombre", read_only=True, default="")

    class Meta:
        model = DiagramaAprobacion
        fields = ["id", "accion", "user", "user_username",
                  "aprobador_destinado", "aprobador_destinado_username",
                  "modulo", "modulo_nombre", "comentario", "fecha"]
        read_only_fields = fields


class DiagramaSerializer(serializers.ModelSerializer):
    creado_por_username = serializers.CharField(source="creado_por.username", read_only=True, default="")
    mi_permiso = serializers.SerializerMethodField()
    compartidos = CompartidoSerializer(many=True, read_only=True)
    historial_aprobacion = AprobacionEventoSerializer(many=True, read_only=True)
    aprobador_username = serializers.CharField(source="aprobador.username", read_only=True, default="")
    decidido_por_username = serializers.CharField(source="decidido_por.username", read_only=True, default="")
    modulo_codigo = serializers.CharField(source="modulo_vinculado.codigo", read_only=True, default="")
    modulo_nombre = serializers.CharField(source="modulo_vinculado.nombre", read_only=True, default="")
    es_inmutable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Diagrama
        fields = ["id", "titulo", "descripcion", "data", "publico", "miniatura",
                  "creado", "actualizado", "creado_por", "creado_por_username",
                  "mi_permiso", "compartidos", "historial_aprobacion",
                  "estado", "aprobador", "aprobador_username",
                  "enviado_aprobacion_en", "visto_por_aprobador_en",
                  "decidido_en", "decidido_por", "decidido_por_username",
                  "comentario_decision",
                  "modulo_vinculado", "modulo_codigo", "modulo_nombre",
                  "es_inmutable"]
        read_only_fields = ["creado", "actualizado", "creado_por", "creado_por_username",
                            "mi_permiso", "compartidos", "historial_aprobacion",
                            "estado", "aprobador", "aprobador_username",
                            "enviado_aprobacion_en", "visto_por_aprobador_en",
                            "decidido_en", "decidido_por",
                            "decidido_por_username", "comentario_decision",
                            "modulo_vinculado", "modulo_codigo", "modulo_nombre",
                            "es_inmutable"]

    def get_mi_permiso(self, d: Diagrama) -> str:
        return _mi_permiso(d, self.context.get("request"))
