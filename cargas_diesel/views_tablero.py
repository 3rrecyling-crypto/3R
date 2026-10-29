"""
Tablero BI de cargas de diésel (Next: /diesel/tablero).

Dos secciones con los mismos filtros (rango de fechas y patio):
  - 3R RECYCLING (flota propia): sus unidades y thermos.
  - Permisionarios: cada uno con sus cargas (las cargas sin permisionario van
    en su propia fila).
La sección sale del nombre de permisionario que se guardó en cada carga, así
que una carga no cambia de sección si después se edita el catálogo.

El costo de cada carga es litros × precio por litro del tótem del que salió
(el precio de la última compra de diésel que entró a ese tótem antes de la
carga; se guarda al registrarla). Las cargas sin compra previa quedan sin precio.
"""
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AjusteInventario, CargaDiesel, CompraCombustible, es_3r_nombre
from .views import get_patios_usuario

MAX_DIAS = 366
ULTIMAS = 50  # filas de detalle por sección / permisionario / compras / ajustes
FOTOS = [
    ('foto_bomba', 'Foto inicio (Bomba)'), ('foto_bomba_final', 'Foto final (Bomba)'), ('foto_odometro', 'Odómetro'),
    ('foto_thermo', 'Foto inicio (Thermo)'), ('foto_thermo_final', 'Foto final (Thermo)'),
    ('foto_horas_thermo', 'Horas del thermo'), ('foto_sticker', 'Sticker'), ('foto_motor', 'Motor'),
]


def puede_ver(user):
    return user.is_superuser or user.has_perm('ternium.acceso_diesel')


def rango(desde_txt, hasta_txt):
    """(desde, hasta) de los textos AAAA-MM-DD; por defecto, el mes en curso."""
    hoy = timezone.localdate()
    hasta = parse_date(hasta_txt or '') or hoy
    desde = parse_date(desde_txt or '') or hasta.replace(day=1)
    if desde > hasta:
        desde, hasta = hasta, desde
    if (hasta - desde).days > MAX_DIAS:
        desde = hasta - timedelta(days=MAX_DIAS)
    return desde, hasta


def _totem(c):
    totem = getattr(c.patio, 'totem', None)  # todo patio tiene tótem; por si acaso
    return totem.nombre if totem else c.patio.nombre


def _url(archivo):
    """URL del archivo, o None si no hay o el almacenamiento falla (la página sigue)."""
    if not archivo:
        return None
    try:
        return archivo.url
    except Exception:
        return None


def _fotos(c):
    fijas = [{'nombre': nombre, 'url': url} for campo, nombre in FOTOS if (url := _url(getattr(c, campo)))]
    extra = [{'nombre': f'Complementaria {n}', 'url': url}
             for n, f in enumerate(c.fotos_complementarias.all(), 1) if (url := _url(f.foto))]
    return fijas + extra


class _Acumulado:
    """Suma litros, cargas, km y costo; el rendimiento es km / litros de las cargas con rendimiento."""

    def __init__(self):
        self.cargas = self.cargas_unidad = self.cargas_thermo = self.sin_precio = 0
        self.litros_unidad = self.litros_thermo = self.costo = self.litros_con_precio = 0.0
        self.km = self.litros_con_rend = 0.0

    def sumar(self, c):
        self.cargas += 1
        if c.tipo_carga == 'thermo':
            self.cargas_thermo += 1
        else:
            self.cargas_unidad += 1
        litros = float(c.litros_diesel + c.litros_thermo)
        self.litros_unidad += float(c.litros_diesel)
        self.litros_thermo += float(c.litros_thermo)
        self.costo += float(c.costo_total)
        if c.precio_litro:
            self.litros_con_precio += litros
        elif litros:
            self.sin_precio += 1
        if c.rendimiento is not None and c.litros_diesel:
            self.km += float(c.rendimiento) * float(c.litros_diesel)
            self.litros_con_rend += float(c.litros_diesel)

    @property
    def litros(self):
        return self.litros_unidad + self.litros_thermo

    @property
    def rendimiento(self):
        return round(self.km / self.litros_con_rend, 2) if self.litros_con_rend else None

    def dict(self, con_rendimiento=True):
        """con_rendimiento=False para permisionarios: son unidades ajenas, no manejan rendimiento."""
        d = {
            'cargas': self.cargas, 'cargas_unidades': self.cargas_unidad, 'cargas_thermos': self.cargas_thermo,
            'litros': round(self.litros, 2), 'litros_unidades': round(self.litros_unidad, 2),
            'litros_thermos': round(self.litros_thermo, 2), 'costo': round(self.costo, 2),
            # Precio por litro promedio de lo cargado (ponderado por litros) y cargas sin precio.
            'precio_promedio': round(self.costo / self.litros_con_precio, 4) if self.litros_con_precio else None,
            'cargas_sin_precio': self.sin_precio,
        }
        if con_rendimiento:
            d.update(km=round(self.km, 1), rendimiento=self.rendimiento)
        return d


def _fila(c, con_rendimiento=True):
    fila = {
        'id': c.pk,
        'fecha': timezone.localtime(c.fecha_carga).strftime('%Y-%m-%d %H:%M'),
        'equipo': c.equipo,
        'tipo': c.tipo_carga,
        'patio': c.patio.nombre,
        'totem': _totem(c),
        'despachador': c.usuario.get_full_name() or c.usuario.username,
        'operador': c.operador_nombre,
        'permisionario': c.permisionario_nombre or 'Sin permisionario',
        'odometro': float(c.odometro) if c.odometro is not None else None,
        'hrs_thermo': float(c.hrs_thermo) if c.hrs_thermo else None,
        'litros': float(c.litros_diesel + c.litros_thermo),
        'precio_litro': float(c.precio_litro) if c.precio_litro else None,
        'costo': float(c.costo_total),
        'fotos': _fotos(c),
    }
    if con_rendimiento:
        fila['rendimiento'] = float(c.rendimiento) if c.rendimiento is not None else None
    return fila


def datos_tablero(user, desde, hasta, patio_id=None):
    """Todo el tablero para el periodo y patio (solo los patios del usuario)."""
    patios = get_patios_usuario(user)
    cargas = CargaDiesel.objects.filter(
        patio__in=patios, fecha_carga__date__gte=desde, fecha_carga__date__lte=hasta,
    ).select_related('unidad', 'thermo', 'patio__totem', 'usuario').prefetch_related('fotos_complementarias') \
        .order_by('-fecha_carga', '-pk')
    patio_id = int(patio_id) if patio_id and str(patio_id).isdigit() else None
    if patio_id:
        cargas = cargas.filter(patio_id=patio_id)

    dias = [desde + timedelta(days=n) for n in range((hasta - desde).days + 1)]
    indice = {d: i for i, d in enumerate(dias)}

    total = _Acumulado()
    flota = _Acumulado()
    flota_dia = [[0.0, 0.0, 0.0, 0.0, 0] for _ in dias]  # [litros unidades, litros thermos, costo, km, cargas]
    equipos = defaultdict(lambda: {'acum': _Acumulado(), 'ultima': None})
    flota_filas = []

    otros = _Acumulado()
    otros_dia = [[0.0, 0.0, 0] for _ in dias]  # [litros, costo, cargas]
    perms = defaultdict(lambda: {
        'acum': _Acumulado(), 'dia': [0.0] * len(dias), 'unidades': set(), 'thermos': set(), 'filas': [],
    })

    for c in cargas:
        total.sumar(c)
        i = indice.get(timezone.localtime(c.fecha_carga).date())
        if es_3r_nombre(c.permisionario_nombre):
            flota.sumar(c)
            if i is not None:
                dia = flota_dia[i]
                dia[0] += float(c.litros_diesel)
                dia[1] += float(c.litros_thermo)
                dia[2] += float(c.costo_total)
                if c.rendimiento is not None:
                    dia[3] += float(c.rendimiento) * float(c.litros_diesel)
                dia[4] += 1
            e = equipos[(c.tipo_carga, c.equipo)]
            e['acum'].sumar(c)
            e['ultima'] = e['ultima'] or timezone.localtime(c.fecha_carga).strftime('%Y-%m-%d %H:%M')
            if len(flota_filas) < ULTIMAS:
                flota_filas.append(_fila(c))
        else:
            otros.sumar(c)
            litros = float(c.litros_diesel + c.litros_thermo)
            clave = (c.permisionario_id, c.permisionario_nombre or 'Sin permisionario')
            p = perms[clave]
            p['acum'].sumar(c)
            (p['thermos'] if c.tipo_carga == 'thermo' else p['unidades']).add(c.equipo)
            if i is not None:
                p['dia'][i] += litros
                otros_dia[i][0] += litros
                otros_dia[i][1] += float(c.costo_total)
                otros_dia[i][2] += 1
            if len(p['filas']) < ULTIMAS:
                p['filas'].append(_fila(c, con_rendimiento=False))

    lista = []
    for (pid, nombre), p in perms.items():
        a = p['acum']
        lista.append({
            'id': pid, 'nombre': nombre, 'sin_permisionario': pid is None and nombre == 'Sin permisionario',
            **a.dict(con_rendimiento=False),
            'porcentaje': round(a.litros / otros.litros * 100, 1) if otros.litros else 0,
            'unidades': len(p['unidades']), 'thermos': len(p['thermos']),
            'por_dia': [round(v, 2) for v in p['dia']],
            'cargas_detalle': p['filas'],
        })
    lista.sort(key=lambda x: (x['sin_permisionario'], -x['litros']))

    return {
        **_compras_ajustes_totems(patios, desde, hasta, patio_id),
        'periodo': {'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'dias': [d.isoformat() for d in dias]},
        'patios': [{'id': p.pk, 'nombre': p.nombre} for p in patios],
        'patio': patio_id,
        'total': total.dict(),
        'flota_3r': {
            'kpis': {**flota.dict(), 'equipos': len(equipos)},
            'por_dia': [{'fecha': d.isoformat(), 'unidades': round(u, 2), 'thermos': round(t, 2),
                         'costo': round(costo, 2), 'km': round(km, 1), 'cargas': n}
                        for d, (u, t, costo, km, n) in zip(dias, flota_dia)],
            'equipos': sorted(({
                'equipo': eq, 'tipo': tipo, **e['acum'].dict(), 'ultima_carga': e['ultima'],
            } for (tipo, eq), e in equipos.items()), key=lambda x: -x['litros']),
            'cargas': flota_filas,
        },
        'permisionarios': {
            'kpis': {**otros.dict(con_rendimiento=False), 'permisionarios': sum(1 for x in lista if not x['sin_permisionario'])},
            'por_dia': [{'fecha': d.isoformat(), 'litros': round(v, 2), 'costo': round(costo, 2), 'cargas': n}
                        for d, (v, costo, n) in zip(dias, otros_dia)],
            'lista': lista,
        },
    }


def _compras_ajustes_totems(patios, desde, hasta, patio_id):
    """Compras y ajustes de diésel del periodo, y cómo está hoy cada tótem (nivel y precio vigente)."""
    if patio_id:
        patios = patios.filter(pk=patio_id)
    rango_fechas = {'patio__in': patios, 'fecha__date__gte': desde, 'fecha__date__lte': hasta}
    hora = lambda f: timezone.localtime(f).strftime('%Y-%m-%d %H:%M')  # noqa: E731
    quien = lambda u: u.get_full_name() or u.username  # noqa: E731

    compras = list(CompraCombustible.objects.filter(tipo='diesel', **rango_fechas)
                   .select_related('patio__totem', 'usuario').order_by('-fecha', '-pk'))
    litros_c = sum(float(c.litros) for c in compras)
    total_c = sum(float(c.total) for c in compras)
    precios = [float(c.precio_unitario) for c in compras]

    ajustes = list(AjusteInventario.objects.filter(tipo_combustible='diesel', **rango_fechas)
                   .select_related('patio__totem', 'usuario').order_by('-fecha', '-pk'))
    entradas = sum(float(a.litros) for a in ajustes if a.tipo_movimiento == 'entrada')
    salidas = sum(float(a.litros) for a in ajustes if a.tipo_movimiento != 'entrada')

    totems = []
    for p in patios.select_related('totem'):
        t = getattr(p, 'totem', None)
        if not t:
            continue
        ultima = CompraCombustible.objects.filter(patio=p, tipo='diesel').order_by('-fecha', '-pk').first()
        precio = float(ultima.precio_unitario) if ultima else None
        totems.append({
            'patio': p.nombre, 'totem': t.nombre,
            'capacidad': float(t.capacidad_diesel), 'cantidad': float(t.cantidad_diesel),
            'porcentaje': t.porcentaje_diesel(), 'estado': t.estado_diesel(), 'alerta': t.alerta_activa_diesel(),
            'precio_litro': precio, 'precio_desde': hora(ultima.fecha) if ultima else None,
            'valor_inventario': round(float(t.cantidad_diesel) * precio, 2) if precio else None,
        })

    return {
        'compras': {
            'kpis': {
                'compras': len(compras), 'litros': round(litros_c, 2), 'total': round(total_c, 2),
                'precio_promedio': round(total_c / litros_c, 4) if litros_c else None,
                'precio_min': min(precios) if precios else None, 'precio_max': max(precios) if precios else None,
            },
            'lista': [{
                'id': c.pk, 'fecha': hora(c.fecha), 'patio': c.patio.nombre, 'totem': _totem(c),
                'proveedor': c.proveedor_nombre or '—', 'litros': float(c.litros),
                'precio_litro': float(c.precio_unitario), 'total': float(c.total),
                'factura': c.numero_factura, 'factura_url': _url(c.factura_pdf), 'usuario': quien(c.usuario),
            } for c in compras[:ULTIMAS]],
        },
        'ajustes': {
            'kpis': {'ajustes': len(ajustes), 'entradas': round(entradas, 2), 'salidas': round(salidas, 2),
                     'neto': round(entradas - salidas, 2)},
            'lista': [{
                'id': a.pk, 'fecha': hora(a.fecha), 'patio': a.patio.nombre, 'totem': _totem(a),
                'movimiento': a.tipo_movimiento, 'litros': float(a.litros), 'motivo': a.motivo,
                'antes': float(a.cantidad_anterior), 'despues': float(a.cantidad_posterior), 'usuario': quien(a.usuario),
            } for a in ajustes[:ULTIMAS]],
        },
        'totems': totems,
    }


class TableroDieselAPIView(APIView):
    """GET ?desde=AAAA-MM-DD&hasta=AAAA-MM-DD&patio=<id> (por defecto: el mes en curso, todos los patios)."""

    def get(self, request):
        if not puede_ver(request.user):
            return Response({'detail': 'No tienes acceso a Control Diésel.'}, status=status.HTTP_403_FORBIDDEN)
        desde, hasta = rango(request.GET.get('desde'), request.GET.get('hasta'))
        return Response(datos_tablero(request.user, desde, hasta, request.GET.get('patio')))
