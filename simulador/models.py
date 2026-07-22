"""Simulador Inteligente de Viajes.

Guarda cada simulación tal cual la armó el usuario (`data`: origen, destino,
paradas, unidad, costos…) más un resumen ejecutivo (`resultado`: km, tiempo,
costo, utilidad, margen) para listar/comparar sin re-simular. Una simulación
marcada como plantilla sirve para rutas o clientes frecuentes.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class SimulacionViaje(models.Model):
    nombre = models.CharField(max_length=180)
    es_plantilla = models.BooleanField(default=False)
    data = models.JSONField(default=dict)        # captura completa del formulario
    resultado = models.JSONField(default=dict)   # KPIs calculados al guardar
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="simulaciones_viaje",
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizado"]
        verbose_name = "Simulación de viaje"
        verbose_name_plural = "Simulaciones de viaje"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.nombre} ({'plantilla' if self.es_plantilla else 'simulación'})"
