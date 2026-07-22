"""Diagramas / flowcharts del ERP con flujo de aprobacion.

Guardamos la representacion del editor (React Flow) tal cual en `data`:
    { "nodes": [...], "edges": [...], "viewport": {...} }
Eso permite versionar y exportar en cualquier momento sin parsear forma a forma.

Flujo de aprobacion:
    BORRADOR -> (enviar) -> EN_REVISION -> (aprobar|rechazar) -> APROBADO|RECHAZADO
Un diagrama APROBADO y vinculado a un modulo no se puede eliminar.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class Diagrama(models.Model):
    ESTADO_BORRADOR = "BORRADOR"
    ESTADO_EN_REVISION = "EN_REVISION"
    ESTADO_APROBADO = "APROBADO"
    ESTADO_RECHAZADO = "RECHAZADO"
    ESTADO_CHOICES = [
        (ESTADO_BORRADOR, "Borrador"),
        (ESTADO_EN_REVISION, "En revision"),
        (ESTADO_APROBADO, "Aprobado"),
        (ESTADO_RECHAZADO, "Rechazado"),
    ]

    titulo = models.CharField(max_length=160)
    descripcion = models.CharField(max_length=400, blank=True)
    data = models.JSONField(default=dict)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="diagramas_creados",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)
    # Compartido: si es False solo lo ve el creador. Si True, todos los usuarios
    # del ERP lo ven (en este MVP es una flag simple).
    publico = models.BooleanField(default=False)
    miniatura = models.TextField(
        blank=True,
        help_text="data:image/png;base64,... opcional para preview en la lista.",
    )

    # ── Flujo de aprobacion ────────────────────────────────────────────────
    estado = models.CharField(
        max_length=15, choices=ESTADO_CHOICES, default=ESTADO_BORRADOR, db_index=True,
    )
    aprobador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="diagramas_a_aprobar",
        help_text="Usuario designado para aprobar el diagrama actual.",
    )
    enviado_aprobacion_en = models.DateTimeField(null=True, blank=True)
    visto_por_aprobador_en = models.DateTimeField(
        null=True, blank=True,
        help_text="Primera vez que el aprobador designado abrio el diagrama en revision.",
    )
    decidido_en = models.DateTimeField(null=True, blank=True)
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="diagramas_decididos",
    )
    comentario_decision = models.CharField(max_length=600, blank=True)

    # Vinculacion a modulo del ERP: cuando es APROBADO se puede asociar a un
    # modulo y todos los usuarios con acceso a ese modulo lo veran.
    # Vinculación a módulo ERP (funcionalidad de SANBENITO no aplicable a 3r):
    # se conserva el campo como id opcional, sin FK.
    modulo_vinculado = models.IntegerField(null=True, blank=True, default=None)

    class Meta:
        ordering = ["-actualizado"]
        indexes = [models.Index(fields=["estado", "modulo_vinculado"])]

    def __str__(self) -> str:
        return self.titulo or f"Diagrama #{self.pk}"

    @property
    def es_inmutable(self) -> bool:
        """Aprobado y vinculado a un modulo -> protegido contra borrado/edicion estructural."""
        return self.estado == self.ESTADO_APROBADO and self.modulo_vinculado is not None


class PlantillaCanvas(models.Model):
    """Plantilla reutilizable del Canvas Pro.

    Dos ambitos:
      - 'global'   -> PREDETERMINADA. Solo staff/superuser puede crear/editar/
                      borrar. La ven TODOS los usuarios con acceso al modulo.
      - 'personal' -> privada del usuario que la creo. Solo el la ve y edita.

    `data` guarda el lienzo: { "tipo": "plantilla", "elements": [...], "bg"?: "#.." }.
    """
    AMBITO_GLOBAL = "global"
    AMBITO_PERSONAL = "personal"
    AMBITO_CHOICES = [
        (AMBITO_GLOBAL, "Global (predeterminada)"),
        (AMBITO_PERSONAL, "Personal"),
    ]

    titulo = models.CharField(max_length=160, default="Plantilla")
    descripcion = models.CharField(max_length=400, blank=True, default="")
    categoria = models.CharField(max_length=80, blank=True, default="Mis plantillas")
    data = models.JSONField(default=dict)
    miniatura = models.TextField(
        blank=True, default="",
        help_text="data:image/png;base64,... para preview en la galeria.",
    )
    ambito = models.CharField(
        max_length=10, choices=AMBITO_CHOICES, default=AMBITO_PERSONAL, db_index=True,
    )
    orden = models.IntegerField(default=100)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="plantillas_canvas",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ambito", "orden", "-actualizado"]
        indexes = [models.Index(fields=["ambito"])]

    def __str__(self) -> str:
        return self.titulo or f"Plantilla #{self.pk}"


class DiagramaCompartido(models.Model):
    """Comparte un diagrama con un usuario especifico, con un permiso.

    A diferencia del flag `publico` (que abre el diagrama a todos), aqui el
    propietario elige usuario por usuario y le da permiso de SOLO VER o EDITAR.
    """
    PERMISO_VER = "ver"
    PERMISO_EDITAR = "editar"
    PERMISO_CHOICES = [
        (PERMISO_VER, "Solo ver"),
        (PERMISO_EDITAR, "Puede editar"),
    ]

    diagrama = models.ForeignKey(
        Diagrama, on_delete=models.CASCADE, related_name="compartidos",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="diagramas_compartidos_conmigo",
    )
    permiso = models.CharField(max_length=10, choices=PERMISO_CHOICES, default=PERMISO_VER)
    compartido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="diagramas_que_compartio",
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("diagrama", "usuario")
        ordering = ["-creado"]

    def __str__(self) -> str:
        return f"{self.diagrama_id} -> {self.usuario_id} ({self.permiso})"


class DiagramaAprobacion(models.Model):
    """Historial inmutable de eventos de aprobacion sobre un diagrama.

    Cada envio/aprobacion/rechazo genera una fila. Sirve para auditar quien
    aprobo que y cuando, y para mostrar el timeline en la UI.
    """
    ACCION_ENVIO = "ENVIO"
    ACCION_VISTO = "VISTO"
    ACCION_APROBAR = "APROBAR"
    ACCION_RECHAZAR = "RECHAZAR"
    ACCION_VINCULAR = "VINCULAR"
    ACCION_DESVINCULAR = "DESVINCULAR"
    ACCION_CHOICES = [
        (ACCION_ENVIO, "Envio a aprobacion"),
        (ACCION_VISTO, "Visto por el aprobador"),
        (ACCION_APROBAR, "Aprobado"),
        (ACCION_RECHAZAR, "Rechazado"),
        (ACCION_VINCULAR, "Vinculado a modulo"),
        (ACCION_DESVINCULAR, "Desvinculado de modulo"),
    ]

    diagrama = models.ForeignKey(
        Diagrama, on_delete=models.CASCADE, related_name="historial_aprobacion",
    )
    accion = models.CharField(max_length=15, choices=ACCION_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="diagramas_acciones",
    )
    aprobador_destinado = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
        help_text="Cuando accion=ENVIO, a quien se le solicito aprobar.",
    )
    modulo = models.IntegerField(null=True, blank=True, default=None)
    comentario = models.CharField(max_length=600, blank=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self) -> str:
        return f"{self.diagrama_id} {self.accion} {self.fecha:%Y-%m-%d %H:%M}"
