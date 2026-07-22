"""Genera claves de licencia PREMIUM válidas (para vender/entregar a clientes).

    python manage.py generar_licencias        → 1 clave
    python manage.py generar_licencias 10     → 10 claves
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from herramientas.licencias import clave_valida, generar_clave


class Command(BaseCommand):
    help = "Genera claves de licencia PREMIUM válidas."

    def add_arguments(self, parser):
        parser.add_argument("n", nargs="?", type=int, default=1)

    def handle(self, *args, **opts):
        n = max(1, min(1000, opts["n"]))
        for _ in range(n):
            clave = generar_clave()
            assert clave_valida(clave)
            self.stdout.write(clave)
        self.stdout.write(self.style.SUCCESS(f"{n} clave(s) generada(s)."))
