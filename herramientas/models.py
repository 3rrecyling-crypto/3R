from django.db import models

# Create your models here.


class LicenciaPremium(models.Model):
    """Licencia PREMIUM de las herramientas de paga (una activación habilita a
    todos los usuarios). La clave se valida OFFLINE (herramientas/licencias.py);
    se generan con `python manage.py generar_licencias`."""
    clave = models.CharField(max_length=40, unique=True)
    activada_en = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["-activada_en"]

    def __str__(self):
        return f"Licencia {self.clave} ({'activa' if self.activa else 'inactiva'})"
