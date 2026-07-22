"""Transferencias de archivos con link público de 24 horas (tipo WeTransfer).

Seguridad:
  - El token es de 256 bits (secrets.token_urlsafe) — imposible de adivinar.
  - Los blobs se guardan con nombre ANÓNIMO (uuid, sin extensión): aunque el
    bucket/carpeta se listara, no se sabe qué es cada archivo.
  - El público NUNCA toca el storage directo: descarga a través del backend,
    que valida token + expiración y sirve con Content-Disposition seguro.
  - Expiración dura de 24 h validada en servidor; los blobs expirados se
    purgan de forma perezosa en cada uso del módulo.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def _token() -> str:
    return secrets.token_urlsafe(32)  # 43 chars URL-safe, 256 bits


def _ruta_archivo(instance: "ArchivoTransferencia", filename: str) -> str:
    # Nombre de storage anónimo: el nombre real vive SOLO en la base de datos.
    return f"transferencias/{uuid.uuid4().hex}"


class Transferencia(models.Model):
    token = models.CharField(max_length=64, unique=True, default=_token, editable=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transferencias"
    )
    titulo = models.CharField(max_length=140, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField(db_index=True)
    descargas = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-creado_en"]

    def save(self, *args, **kwargs):
        if not self.expira_en:
            self.expira_en = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    @property
    def expirada(self) -> bool:
        return timezone.now() >= self.expira_en

    def borrar_blobs(self) -> None:
        for a in self.archivos.all():
            try:
                a.archivo.delete(save=False)
            except Exception:
                pass  # el blob ya no existe: no bloquea el borrado del registro

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.titulo or self.token[:8]} ({self.creado_por})"


class ArchivoTransferencia(models.Model):
    transferencia = models.ForeignKey(
        Transferencia, on_delete=models.CASCADE, related_name="archivos"
    )
    archivo = models.FileField(upload_to=_ruta_archivo, max_length=300)
    nombre = models.CharField(max_length=255)  # nombre original (solo en BD)
    tamano = models.BigIntegerField(default=0)

    def __str__(self) -> str:  # pragma: no cover
        return self.nombre
