"""
Importa cargas de diésel de un control anterior (Excel pasado a JSON) SIN descontarlas del
tótem, sin costo y sin mandar correos.

    python manage.py importar_cargas_diesel /tmp/cargas.json --patio "PATIO MONTERREY" --usuario <tu_usuario>
    python manage.py importar_cargas_diesel /tmp/cargas.json --patio "PATIO MONTERREY" --usuario <tu_usuario> --aplicar

Sin --aplicar solo simula: hace todo y al final lo deshace, así se ve exactamente qué pasaría.

El JSON es una lista de filas:
    {"fila": 994, "fecha": "2026-10-01", "permisionario": "3R RECYCLING", "despachador": "ANGEL",
     "unidad": "T-01", "thermo": null, "operador": "EDUARDO", "km": null, "litros": 175}

- Unidad: la del permisionario con ese número (las de Catálogos se llaman "T-01" o "T-01 (MOVEX)").
  Si el permisionario no la tiene, se da de alta en Catálogos como "T-01 (PERMISIONARIO)" y se le asigna.
- Thermo: el texto tal cual (como en la captura); si no existe, se da de alta.
- Despachador: el usuario con ese nombre o usuario; si no hay uno solo, queda a nombre de --usuario.
- Fecha: ese día a las 12:00 (el control no trae hora).
- Si se vuelve a correr, no duplica: salta las cargas que ya existan (mismo patio, día, equipo,
  litros y operador).
"""
import json
import re
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ternium.models import Unidad as UnidadCatalogo

from ...models import CargaDiesel, Patio, Permisionario, PermisionarioUnidad, Thermo, Unidad, es_3r_nombre
from ...views_captura import normalizar_thermo


class Simulacion(Exception):
    pass


def _texto(v):
    return ' '.join(str(v or '').split()).upper()


def _base(internal_id):
    """Número de la unidad sin el "(PERMISIONARIO)" o las placas del final."""
    return _texto(re.sub(r'\s*\([^)]*\)\s*$', '', internal_id or ''))


class Command(BaseCommand):
    help = 'Importa cargas de diésel de un JSON sin descontar del tótem (simula si no se pasa --aplicar).'

    def add_arguments(self, parser):
        parser.add_argument('archivo')
        parser.add_argument('--patio', required=True, help='Nombre del patio, p. ej. "PATIO MONTERREY"')
        parser.add_argument('--usuario', required=True, help='Tu usuario: las cargas sin despachador conocido quedan a tu nombre')
        parser.add_argument('--aplicar', action='store_true', help='Guardar de verdad (sin esto solo simula)')

    def handle(self, *args, **o):
        try:
            with open(o['archivo'], encoding='utf-8') as f:
                filas = json.load(f)
        except (OSError, ValueError) as e:
            raise CommandError(f'No se pudo leer el JSON: {e}')
        patio = Patio.objects.filter(nombre__iexact=o['patio'].strip()).first()
        if not patio:
            raise CommandError(f'No existe el patio "{o["patio"]}". Patios: {", ".join(Patio.objects.values_list("nombre", flat=True))}')
        importa = User.objects.filter(username=o['usuario']).first()
        if not importa:
            raise CommandError(f'No existe el usuario "{o["usuario"]}".')

        self.avisos, self.errores = [], []
        self.unidades_nuevas, self.thermos_nuevos, self.despachadores = [], [], {}
        creadas = saltadas = 0
        litros_total = Decimal('0')
        filas = sorted(filas, key=lambda r: (str(r.get('fecha')), r.get('fila') or 0))
        try:
            with transaction.atomic():
                vistas = Counter()
                for r in filas:
                    fila = r.get('fila', '?')
                    try:
                        carga, clave = self._preparar(r, patio, importa)
                    except ValueError as e:
                        self.errores.append(f'fila {fila}: {e}')
                        continue
                    # No duplicar si ya se importó (cuenta repeticiones legítimas dentro del archivo)
                    vistas[clave] += 1
                    if vistas[clave] <= self._existentes(clave):
                        saltadas += 1
                        self.stdout.write(f'  fila {fila}: ya existe, se salta')
                        continue
                    carga.save()
                    dia = timezone.make_aware(datetime.combine(carga._dia, time(12, 0)))
                    CargaDiesel.objects.filter(pk=carga.pk).update(fecha_carga=dia)
                    carga.fecha_carga = dia
                    if carga.odometro is not None:
                        rend = carga.calcular_rendimiento()
                        if rend is not None:
                            CargaDiesel.objects.filter(pk=carga.pk).update(rendimiento=rend)
                    creadas += 1
                    litros = carga.litros_thermo if carga.tipo_carga == 'thermo' else carga.litros_diesel
                    litros_total += litros
                    self.stdout.write(f'  fila {fila}: {carga._dia:%d/%m/%Y} · {carga.permisionario_nombre or "sin permisionario"} · '
                                      f'{"Thermo " + carga.thermo.identificador if carga.thermo_id else "Unidad " + carga.unidad.numero_economico}'
                                      f' · {litros:g} L · {carga.operador_nombre or "—"} · despachó {carga.usuario.get_full_name() or carga.usuario.username}')
                self._resumen(creadas, saltadas, litros_total, o['aplicar'])
                if not o['aplicar']:
                    raise Simulacion
        except Simulacion:
            self.stdout.write(self.style.WARNING('\nSIMULACIÓN: no se guardó nada. Si todo se ve bien, corre lo mismo con --aplicar.'))
            return
        self.stdout.write(self.style.SUCCESS(f'\nLISTO: se guardaron {creadas} cargas. El tótem no se tocó.'))

    # ── una fila → carga (sin guardar) ──
    def _preparar(self, r, patio, importa):
        try:
            dia = date.fromisoformat(str(r.get('fecha')))
        except ValueError:
            raise ValueError(f'fecha inválida "{r.get("fecha")}"')
        try:
            litros = Decimal(str(r.get('litros')))
        except InvalidOperation:
            raise ValueError(f'litros inválidos "{r.get("litros")}"')
        if litros <= 0:
            raise ValueError('sin litros')
        nombre_perm = _texto(r.get('permisionario'))
        permisionario = None
        if nombre_perm:
            permisionario = Permisionario.objects.filter(nombre__iexact=nombre_perm).order_by('-activo', 'pk').first()
            if not permisionario:
                raise ValueError(f'no existe el permisionario "{nombre_perm}" (dalo de alta en Catálogos y vuelve a correr)')
        if dia > timezone.localdate():
            self.avisos.append(f'fila {r.get("fila")}: fecha futura {dia:%d/%m/%Y}')

        unidad = thermo = None
        if r.get('thermo'):
            thermo = self._thermo(r['thermo'])
        elif r.get('unidad'):
            if not permisionario:
                raise ValueError('una unidad sin permisionario no se puede dar de alta')
            unidad = self._unidad(_texto(r['unidad']), permisionario, patio)
        else:
            raise ValueError('sin unidad ni thermo')

        usuario = self._despachador(_texto(r.get('despachador')), importa)
        es_thermo = thermo is not None
        km = r.get('km')
        odometro = None
        if km not in (None, '') and not es_thermo and permisionario and es_3r_nombre(permisionario.nombre):
            try:
                odometro = Decimal(str(km))
            except InvalidOperation:
                self.avisos.append(f'fila {r.get("fila")}: kilometraje inválido "{km}" (se omite)')
        carga = CargaDiesel(
            patio=patio, unidad=unidad, thermo=thermo, usuario=usuario, persona_relleno=usuario,
            tipo_carga='thermo' if es_thermo else 'unidad', odometro=odometro,
            litros_diesel=0 if es_thermo else litros, litros_thermo=litros if es_thermo else 0,
            permisionario=permisionario, permisionario_nombre=permisionario.nombre if permisionario else '',
            operador_nombre=_texto(r.get('operador'))[:150],
        )
        carga._dia = dia
        clave = (patio.pk, dia, unidad.pk if unidad else None, thermo.pk if thermo else None, litros, carga.operador_nombre)
        return carga, clave

    def _existentes(self, clave):
        patio_id, dia, unidad_id, thermo_id, litros, operador = clave
        inicio = timezone.make_aware(datetime.combine(dia, time.min))
        fin = timezone.make_aware(datetime.combine(dia, time.max))
        qs = CargaDiesel.objects.filter(patio_id=patio_id, fecha_carga__range=(inicio, fin), operador_nombre=operador,
                                        unidad_id=unidad_id, thermo_id=thermo_id)
        qs = qs.filter(Q(litros_thermo=litros) if thermo_id else Q(litros_diesel=litros))
        return qs.count()

    def _unidad(self, numero, permisionario, patio):
        """Unidad de diésel de la unidad de Catálogos de ese permisionario; si no la tiene, la da de alta."""
        for v in PermisionarioUnidad.objects.select_related('unidad').filter(permisionario=permisionario):
            if _base(v.unidad.internal_id) == numero:
                cat = v.unidad
                break
        else:
            nombre = f'{numero} ({permisionario.nombre})'[:100]
            cat = UnidadCatalogo.objects.filter(internal_id__iexact=nombre).first()
            if cat and hasattr(cat, 'permisionario_diesel') and cat.permisionario_diesel.permisionario_id != permisionario.pk:
                raise ValueError(f'"{nombre}" ya existe pero es de {cat.permisionario_diesel.permisionario.nombre}')
            if not cat:
                cat = UnidadCatalogo.objects.create(internal_id=nombre)
                self.unidades_nuevas.append(nombre)
            PermisionarioUnidad.objects.get_or_create(unidad=cat, defaults={'permisionario': permisionario})
            sueltas = UnidadCatalogo.objects.filter(internal_id__iexact=numero).exclude(pk=cat.pk)
            for s in sueltas:
                if not hasattr(s, 'permisionario_diesel'):
                    self.avisos.append(f'"{s.internal_id}" existe en Catálogos sin permisionario; se usó "{cat.internal_id}"')
        unidad = Unidad.para_unidad_catalogo(cat)
        if unidad.patio_id is None:
            unidad.patio = patio
            unidad.save(update_fields=['patio'])
        return unidad

    def _thermo(self, texto):
        identificador = normalizar_thermo(texto)
        thermo, nuevo = Thermo.objects.get_or_create(identificador=identificador)
        if nuevo:
            self.thermos_nuevos.append(identificador)
        return thermo

    def _despachador(self, nombre, importa):
        if nombre not in self.despachadores:
            usuarios = list(User.objects.filter(is_active=True).filter(
                Q(username__iexact=nombre) | Q(first_name__iexact=nombre)))
            if len(usuarios) == 1:
                self.despachadores[nombre] = usuarios[0]
            else:
                self.despachadores[nombre] = importa
                self.avisos.append(f'despachador "{nombre}": {"varios usuarios" if usuarios else "ningún usuario"} con ese nombre; '
                                   f'sus cargas quedan a nombre de {importa.username}')
        return self.despachadores[nombre]

    def _resumen(self, creadas, saltadas, litros, aplicar):
        w = self.stdout.write
        w('\n' + '=' * 70)
        w(f'Cargas {"guardadas" if aplicar else "a guardar"}: {creadas} · {litros:,.2f} L · ya existían (saltadas): {saltadas}')
        w('Despachadores: ' + ', '.join(f'{n} → {u.get_full_name() or u.username} ({u.username})' for n, u in self.despachadores.items()))
        w(f'Unidades nuevas en Catálogos ({len(self.unidades_nuevas)}): ' + (', '.join(self.unidades_nuevas) or '—'))
        w(f'Thermos nuevos ({len(self.thermos_nuevos)}): ' + (', '.join(self.thermos_nuevos) or '—'))
        w('El tótem NO se toca, sin costo y sin correos.')
        for a in dict.fromkeys(self.avisos):
            w(self.style.WARNING('AVISO  ' + a))
        for e in self.errores:
            w(self.style.ERROR('NO SE IMPORTA  ' + e))
