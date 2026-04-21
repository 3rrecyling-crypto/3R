"""
API JSON para flujo_bancos — consumible desde Next.js.
Endpoints:
  GET  /bancos/api/movimientos/          — lista paginada
  POST /bancos/api/movimientos/crear/    — crear movimiento
  GET  /bancos/api/movimientos/<pk>/     — detalle de un movimiento
  POST /bancos/api/movimientos/importar/ — importar desde Excel
  GET  /bancos/api/cuentas/              — lista de cuentas (para selects)
"""

import json
import os
from decimal import Decimal, InvalidOperation
from io import BytesIO

import openpyxl
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    Cuenta, Movimiento, Categoria, SubCategoria,
    UnidadNegocio, Operacion, ComprobanteFiscal, Tercero,
    ResumenMensual,
)
from .views import (
    _subir_archivo_a_s3,
    procesar_datos_xml_desde_bytes,
    recalcular_iva_movimiento,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_error(msg, status=400):
    return JsonResponse({"ok": False, "error": msg}, status=status)


def _movimiento_to_dict(mov):
    """Serializa un Movimiento a dict plano."""
    comprobantes = []
    for c in mov.comprobantes.all():
        comprobantes.append({
            "id": c.id,
            "uuid": c.uuid,
            "monto_iva": float(c.monto_iva),
            "monto_ret_iva": float(c.monto_ret_iva),
            "monto_ret_isr": float(c.monto_ret_isr),
            "archivo_xml_url": c.archivo_xml.url if c.archivo_xml else None,
            "archivo_pdf_url": c.archivo_pdf.url if c.archivo_pdf else None,
            "fecha_subida": c.fecha_subida.isoformat() if c.fecha_subida else None,
        })

    return {
        "id": mov.id,
        "fecha": mov.fecha.isoformat() if mov.fecha else None,
        "concepto": mov.concepto,
        "cuenta_id": mov.cuenta_id,
        "cuenta_nombre": mov.cuenta.nombre if mov.cuenta else None,
        "cargo": float(mov.cargo),
        "abono": float(mov.abono),
        "saldo_banco": float(mov.saldo_banco) if mov.saldo_banco is not None else None,
        "iva": float(mov.iva),
        "ret_iva": float(mov.ret_iva),
        "ret_isr": float(mov.ret_isr),
        "tercero": mov.tercero,
        "comentarios": mov.comentarios,
        "estatus": mov.estatus,
        "auditado": mov.auditado,
        "categoria_id": mov.categoria_id,
        "categoria_nombre": mov.categoria.nombre if mov.categoria else None,
        "subcategoria_id": mov.subcategoria_id,
        "subcategoria_nombre": mov.subcategoria.nombre if mov.subcategoria else None,
        "unidad_negocio_id": mov.unidad_negocio_id,
        "unidad_negocio_nombre": mov.unidad_negocio.nombre if mov.unidad_negocio else None,
        "operacion_id": mov.operacion_id,
        "operacion_nombre": mov.operacion.nombre if mov.operacion else None,
        "comprobantes": comprobantes,
    }


# ---------------------------------------------------------------------------
# GET /bancos/api/cuentas/
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["GET"])
def api_lista_cuentas(request):
    """Devuelve todas las cuentas (útil para poblar selects en Next.js)."""
    cuentas = Cuenta.objects.all().order_by("nombre")
    data = [
        {
            "id": c.id,
            "nombre": c.nombre,
            "moneda": c.moneda,
            "saldo_actual": float(c.saldo_actual),
        }
        for c in cuentas
    ]
    return JsonResponse({"ok": True, "cuentas": data})


# ---------------------------------------------------------------------------
# GET /bancos/api/movimientos/
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["GET"])
def api_lista_movimientos(request):
    """
    Query params opcionales:
      cuenta, q, fecha_inicio, fecha_fin, estatus, auditado, page, page_size
    """
    qs = Movimiento.objects.select_related(
        "cuenta", "categoria", "subcategoria", "unidad_negocio", "operacion"
    )

    cuenta_id = request.GET.get("cuenta")
    if cuenta_id:
        qs = qs.filter(cuenta_id=cuenta_id)

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(concepto__icontains=q) | Q(tercero__icontains=q))

    fecha_inicio = request.GET.get("fecha_inicio")
    fecha_fin = request.GET.get("fecha_fin")
    if fecha_inicio:
        qs = qs.filter(fecha__gte=fecha_inicio)
    if fecha_fin:
        qs = qs.filter(fecha__lte=fecha_fin)

    estatus = request.GET.get("estatus")
    if estatus:
        qs = qs.filter(estatus=estatus)

    auditado = request.GET.get("auditado")
    if auditado == "1":
        qs = qs.filter(auditado=True)
    elif auditado == "0":
        qs = qs.filter(auditado=False)

    qs = qs.order_by("fecha", "id")

    page_size = min(int(request.GET.get("page_size", 25)), 100)
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    return JsonResponse({
        "ok": True,
        "total": paginator.count,
        "paginas": paginator.num_pages,
        "pagina_actual": page_obj.number,
        "movimientos": [_movimiento_to_dict(m) for m in page_obj],
    })


# ---------------------------------------------------------------------------
# GET /bancos/api/movimientos/<pk>/
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["GET"])
def api_detalle_movimiento(request, pk):
    """Devuelve el detalle completo de un movimiento, incluyendo comprobantes."""
    try:
        mov = Movimiento.objects.select_related(
            "cuenta", "categoria", "subcategoria", "unidad_negocio", "operacion"
        ).prefetch_related("comprobantes").get(pk=pk)
    except Movimiento.DoesNotExist:
        return _json_error("Movimiento no encontrado.", status=404)

    return JsonResponse({"ok": True, "movimiento": _movimiento_to_dict(mov)})


# ---------------------------------------------------------------------------
# POST /bancos/api/movimientos/crear/
# ---------------------------------------------------------------------------
@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_crear_movimiento(request):
    """
    Crea un movimiento con comprobantes (XML/PDF) opcionales.

    Body: multipart/form-data  ó  application/json (sin archivos)

    Campos JSON/form:
      cuenta_id*        int
      fecha*            YYYY-MM-DD
      concepto*         str
      tipo*             "ingreso" | "egreso"
      monto*            decimal
      categoria_id      int (opcional)
      subcategoria_id   int (opcional)
      unidad_negocio_id int (opcional)
      operacion_id      int (opcional)
      tercero           str (opcional)
      comentarios       str (opcional)

    Archivos (multipart):
      archivos_comprobantes   uno o varios XML/PDF
    """
    # -- Leer datos (JSON o form) --
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return _json_error("JSON inválido.")
    else:
        body = request.POST

    # Campos requeridos
    cuenta_id = body.get("cuenta_id")
    fecha_str = body.get("fecha")
    concepto = body.get("concepto", "").strip()
    tipo = body.get("tipo", "egreso")
    monto_raw = body.get("monto", "0")

    if not all([cuenta_id, fecha_str, concepto]):
        return _json_error("Faltan campos requeridos: cuenta_id, fecha, concepto.")

    try:
        cuenta = Cuenta.objects.get(pk=cuenta_id)
    except Cuenta.DoesNotExist:
        return _json_error("Cuenta no encontrada.")

    try:
        from datetime import date
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        return _json_error("Formato de fecha inválido. Use YYYY-MM-DD.")

    try:
        monto = Decimal(str(monto_raw))
    except InvalidOperation:
        return _json_error("Monto inválido.")

    # Campos opcionales
    def _get_fk(model, key):
        val = body.get(key)
        if val:
            try:
                return model.objects.get(pk=int(val))
            except (model.DoesNotExist, ValueError):
                pass
        return None

    categoria = _get_fk(Categoria, "categoria_id")
    subcategoria = _get_fk(SubCategoria, "subcategoria_id")
    unidad_negocio = _get_fk(UnidadNegocio, "unidad_negocio_id")
    operacion = _get_fk(Operacion, "operacion_id")
    tercero = body.get("tercero", "").strip() or None
    comentarios = body.get("comentarios", "").strip() or None

    try:
        with transaction.atomic():
            mov = Movimiento(
                cuenta=cuenta,
                fecha=fecha,
                concepto=concepto,
                cargo=monto if tipo == "egreso" else Decimal("0"),
                abono=monto if tipo == "ingreso" else Decimal("0"),
                categoria=categoria,
                subcategoria=subcategoria,
                unidad_negocio=unidad_negocio,
                operacion=operacion,
                tercero=tercero,
                comentarios=comentarios,
            )
            mov.save()

            # -- Procesar archivos adjuntos --
            archivos = request.FILES.getlist("archivos_comprobantes")
            for archivo in archivos:
                contenido_bytes = archivo.read()
                ext = os.path.splitext(archivo.name)[1].lower()
                ahora = timezone.now()
                carpeta = "xmls" if ext == ".xml" else "pdfs"
                s3_path = f"{carpeta}/{ahora.year}/{ahora.month}/{archivo.name}"

                nuevo_comp = ComprobanteFiscal(movimiento=mov)

                if ext == ".xml":
                    datos = procesar_datos_xml_desde_bytes(contenido_bytes)
                    nuevo_comp.uuid = datos["uuid"]
                    nuevo_comp.monto_iva = datos["iva"]
                    nuevo_comp.monto_ret_iva = datos["ret_iva"]
                    nuevo_comp.monto_ret_isr = datos["ret_isr"]

                memoria = BytesIO(contenido_bytes)
                ruta = _subir_archivo_a_s3(memoria, s3_path)

                if ruta:
                    if ext == ".xml":
                        nuevo_comp.archivo_xml.name = ruta
                    else:
                        nuevo_comp.archivo_pdf.name = ruta
                    nuevo_comp.save()

            if archivos:
                recalcular_iva_movimiento(mov)

    except Exception as e:
        return _json_error(f"Error al crear movimiento: {e}", status=500)

    # Refrescar para obtener datos completos
    mov.refresh_from_db()
    mov = Movimiento.objects.prefetch_related("comprobantes").select_related(
        "cuenta", "categoria", "subcategoria", "unidad_negocio", "operacion"
    ).get(pk=mov.pk)

    return JsonResponse({"ok": True, "movimiento": _movimiento_to_dict(mov)}, status=201)


# ---------------------------------------------------------------------------
# POST /bancos/api/movimientos/importar/
# ---------------------------------------------------------------------------
@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_importar_movimientos(request):
    """
    Importa movimientos desde un archivo Excel (.xlsx).

    Body: multipart/form-data
      cuenta_id*       int
      archivo_excel*   .xlsx file

    Columnas esperadas en el Excel (fila 2 en adelante):
      A: Fecha | B: Concepto | C: Cargo | D: Abono | E: Saldo (opcional)

    Respuesta:
      { ok, creados, omitidos, saldo_actualizado }
    """
    cuenta_id = request.POST.get("cuenta_id")
    archivo = request.FILES.get("archivo_excel")

    if not cuenta_id:
        return _json_error("Falta cuenta_id.")
    if not archivo:
        return _json_error("Falta el archivo Excel.")

    try:
        cuenta = Cuenta.objects.get(pk=cuenta_id)
    except Cuenta.DoesNotExist:
        return _json_error("Cuenta no encontrada.")

    try:
        wb = openpyxl.load_workbook(archivo)
        ws = wb.active

        count_creados = 0
        count_omitidos = 0
        saldo_banco_excel = None

        for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
            fecha_raw = row[0] if len(row) > 0 else None
            if not fecha_raw:
                continue

            concepto = row[1] if len(row) > 1 else None
            cargo_raw = row[2] if len(row) > 2 else None
            abono_raw = row[3] if len(row) > 3 else None

            # Saldo (columna E)
            saldo_renglon = Decimal("0")
            if len(row) >= 5 and row[4] is not None:
                try:
                    val = str(row[4]).replace(",", "").replace("$", "")
                    saldo_renglon = Decimal(val)
                    if i == 0:
                        saldo_banco_excel = saldo_renglon
                except InvalidOperation:
                    pass

            def _to_decimal(val):
                if val is None:
                    return Decimal("0")
                try:
                    return Decimal(str(val).replace(",", "").replace("$", ""))
                except InvalidOperation:
                    return Decimal("0")

            cargo = _to_decimal(cargo_raw)
            abono = _to_decimal(abono_raw)

            existe = Movimiento.objects.filter(
                cuenta=cuenta,
                fecha=fecha_raw,
                concepto=concepto,
                cargo=cargo,
                abono=abono,
            ).exists()

            if existe:
                count_omitidos += 1
                continue

            Movimiento.objects.create(
                cuenta=cuenta,
                fecha=fecha_raw,
                concepto=concepto or "Sin concepto",
                cargo=cargo,
                abono=abono,
                saldo_banco=saldo_renglon,
                estatus="PENDIENTE",
            )
            count_creados += 1

        # Actualizar saldo inicial de la cuenta si se detectó saldo en la col E
        saldo_actualizado = False
        if saldo_banco_excel is not None:
            from django.db.models import Sum
            totales = Movimiento.objects.filter(cuenta=cuenta).aggregate(
                sum_abono=Sum("abono"), sum_cargo=Sum("cargo")
            )
            total_abonos = totales["sum_abono"] or 0
            total_cargos = totales["sum_cargo"] or 0
            cuenta.saldo_inicial = saldo_banco_excel - (total_abonos - total_cargos)
            cuenta.save()
            saldo_actualizado = True

    except Exception as e:
        return _json_error(f"Error al procesar el Excel: {e}", status=500)

    return JsonResponse({
        "ok": True,
        "creados": count_creados,
        "omitidos": count_omitidos,
        "saldo_actualizado": saldo_actualizado,
        "saldo_corte": float(saldo_banco_excel) if saldo_banco_excel is not None else None,
    }, status=201)


# ---------------------------------------------------------------------------
# GET /bancos/api/lookup/   — catálogos para selects
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["GET"])
def api_lookup_data(request):
    """Devuelve categorias, subcategorias, unidades_negocio y operaciones."""
    categorias = list(Categoria.objects.values("id", "nombre").order_by("nombre"))
    subcategorias = list(SubCategoria.objects.values("id", "nombre", "categoria_id").order_by("nombre"))
    unidades = list(UnidadNegocio.objects.values("id", "nombre").order_by("nombre"))
    operaciones = list(Operacion.objects.values("id", "nombre").order_by("nombre"))
    terceros = list(Tercero.objects.values("id", "nombre").order_by("nombre"))
    return JsonResponse({
        "ok": True,
        "categorias": categorias,
        "subcategorias": subcategorias,
        "unidades_negocio": unidades,
        "operaciones": operaciones,
        "terceros": terceros,
    })


# ---------------------------------------------------------------------------
# PUT/DELETE /bancos/api/movimientos/<pk>/editar/
# ---------------------------------------------------------------------------
@csrf_exempt
@login_required
@require_http_methods(["PUT", "DELETE"])
def api_editar_eliminar_movimiento(request, pk):
    try:
        mov = Movimiento.objects.get(pk=pk)
    except Movimiento.DoesNotExist:
        return _json_error("Movimiento no encontrado.", status=404)

    if request.method == "DELETE":
        mov.delete()
        return JsonResponse({"ok": True})

    # PUT — editar
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return _json_error("JSON inválido.")
    else:
        try:
            body = json.loads(request.body)
        except Exception:
            return _json_error("JSON inválido.")

    def _get_fk(model, key):
        val = body.get(key)
        if val:
            try:
                return model.objects.get(pk=int(val))
            except (model.DoesNotExist, ValueError):
                pass
        return None

    if "fecha" in body:
        from datetime import date as _date
        try:
            mov.fecha = _date.fromisoformat(body["fecha"])
        except ValueError:
            return _json_error("Formato de fecha inválido.")
    if "concepto" in body:
        mov.concepto = body["concepto"]
    if "tipo" in body and "monto" in body:
        from decimal import Decimal as _D, InvalidOperation as _IO
        try:
            monto = _D(str(body["monto"]))
        except _IO:
            return _json_error("Monto inválido.")
        if body["tipo"] == "ingreso":
            mov.abono, mov.cargo = monto, _D("0")
        else:
            mov.cargo, mov.abono = monto, _D("0")
    if "categoria_id" in body:
        mov.categoria = _get_fk(Categoria, "categoria_id")
    if "subcategoria_id" in body:
        mov.subcategoria = _get_fk(SubCategoria, "subcategoria_id")
    if "unidad_negocio_id" in body:
        mov.unidad_negocio = _get_fk(UnidadNegocio, "unidad_negocio_id")
    if "operacion_id" in body:
        mov.operacion = _get_fk(Operacion, "operacion_id")
    if "tercero" in body:
        mov.tercero = body["tercero"] or None
    if "comentarios" in body:
        mov.comentarios = body["comentarios"] or None
    if "estatus" in body:
        mov.estatus = body["estatus"]
    if "auditado" in body:
        mov.auditado = bool(body["auditado"])

    mov.save()
    mov.refresh_from_db()
    mov = Movimiento.objects.select_related(
        "cuenta", "categoria", "subcategoria", "unidad_negocio", "operacion"
    ).prefetch_related("comprobantes").get(pk=mov.pk)
    return JsonResponse({"ok": True, "movimiento": _movimiento_to_dict(mov)})


# ---------------------------------------------------------------------------
# Helpers — ResumenMensual
# ---------------------------------------------------------------------------

_RESUMEN_FIELDS = [
    "ingresos_bancos_mxn", "ingresos_bancos_usd",
    "ingresos_efectivo_mxn", "ingresos_efectivo_usd",
    "gastos_bancos_mxn", "gastos_bancos_usd",
    "gastos_efectivo_mxn", "gastos_efectivo_usd",
    "venta_emitida_mxn", "venta_emitida_usd",
    "venta_operativa_mxn", "venta_operativa_usd",
]


def _resumen_to_dict(r):
    d = {"periodo": r.periodo, "tc": float(r.tc), "actualizado": r.actualizado.isoformat()}
    for f in _RESUMEN_FIELDS:
        d[f] = float(getattr(r, f))
    return d


# ---------------------------------------------------------------------------
# GET  /bancos/api/resumen/            — lista
# POST /bancos/api/resumen/            — upsert (crear o actualizar)
# ---------------------------------------------------------------------------
@csrf_exempt
@login_required
@require_http_methods(["GET", "POST"])
def api_resumen_list_create(request):
    if request.method == "GET":
        resumenes = ResumenMensual.objects.all()
        return JsonResponse({"ok": True, "resumenes": [_resumen_to_dict(r) for r in resumenes]})

    # POST — upsert
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("JSON inválido.")

    periodo = body.get("periodo", "").strip()
    if not periodo or len(periodo) != 7:
        return _json_error("Falta periodo válido (YYYY-MM).")

    resumen, _ = ResumenMensual.objects.get_or_create(periodo=periodo)

    tc_raw = body.get("tc")
    if tc_raw is not None:
        try:
            resumen.tc = Decimal(str(tc_raw))
        except InvalidOperation:
            return _json_error("TC inválido.")

    for field in _RESUMEN_FIELDS:
        val = body.get(field)
        if val is not None:
            try:
                setattr(resumen, field, Decimal(str(val)))
            except InvalidOperation:
                return _json_error(f"Valor inválido en {field}.")

    resumen.save()
    return JsonResponse({"ok": True, "resumen": _resumen_to_dict(resumen)})


# ---------------------------------------------------------------------------
# GET    /bancos/api/resumen/<periodo>/  — detalle
# DELETE /bancos/api/resumen/<periodo>/  — eliminar
# ---------------------------------------------------------------------------
@csrf_exempt
@login_required
@require_http_methods(["GET", "DELETE"])
def api_resumen_detail(request, periodo):
    try:
        resumen = ResumenMensual.objects.get(periodo=periodo)
    except ResumenMensual.DoesNotExist:
        if request.method == "GET":
            # Devolver objeto vacío para ese periodo (facilita el frontend)
            return JsonResponse({"ok": True, "resumen": None})
        return _json_error("Resumen no encontrado.", status=404)

    if request.method == "DELETE":
        resumen.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"ok": True, "resumen": _resumen_to_dict(resumen)})


# ---------------------------------------------------------------------------
# CRUD Categorías  /bancos/api/categorias/
# ---------------------------------------------------------------------------
@csrf_exempt
@login_required
@require_http_methods(["GET", "POST"])
def api_categorias(request):
    if request.method == "GET":
        cats = Categoria.objects.prefetch_related("subcategorias").order_by("nombre")
        data = [
            {
                "id": c.id,
                "nombre": c.nombre,
                "subcategorias": list(c.subcategorias.values("id", "nombre").order_by("nombre")),
            }
            for c in cats
        ]
        return JsonResponse({"ok": True, "categorias": data})

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("JSON inválido.")
    nombre = (body.get("nombre") or "").strip()
    if not nombre:
        return _json_error("Nombre requerido.")
    cat = Categoria.objects.create(nombre=nombre)
    return JsonResponse({"ok": True, "categoria": {"id": cat.id, "nombre": cat.nombre, "subcategorias": []}}, status=201)


@csrf_exempt
@login_required
@require_http_methods(["PUT", "DELETE"])
def api_categoria_detail(request, pk):
    try:
        cat = Categoria.objects.get(pk=pk)
    except Categoria.DoesNotExist:
        return _json_error("Categoría no encontrada.", status=404)
    if request.method == "DELETE":
        cat.delete()
        return JsonResponse({"ok": True})
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("JSON inválido.")
    cat.nombre = (body.get("nombre") or cat.nombre).strip()
    cat.save()
    return JsonResponse({"ok": True, "categoria": {"id": cat.id, "nombre": cat.nombre}})


# ---------------------------------------------------------------------------
# CRUD Subcategorías  /bancos/api/subcategorias/
# ---------------------------------------------------------------------------
@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_subcategorias_crear(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("JSON inválido.")
    nombre = (body.get("nombre") or "").strip()
    cat_id = body.get("categoria_id")
    if not nombre or not cat_id:
        return _json_error("nombre y categoria_id requeridos.")
    try:
        cat = Categoria.objects.get(pk=cat_id)
    except Categoria.DoesNotExist:
        return _json_error("Categoría no encontrada.")
    sub = SubCategoria.objects.create(nombre=nombre, categoria=cat)
    return JsonResponse({"ok": True, "subcategoria": {"id": sub.id, "nombre": sub.nombre, "categoria_id": cat.id}}, status=201)


@csrf_exempt
@login_required
@require_http_methods(["PUT", "DELETE"])
def api_subcategoria_detail(request, pk):
    try:
        sub = SubCategoria.objects.get(pk=pk)
    except SubCategoria.DoesNotExist:
        return _json_error("Subcategoría no encontrada.", status=404)
    if request.method == "DELETE":
        sub.delete()
        return JsonResponse({"ok": True})
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return _json_error("JSON inválido.")
    sub.nombre = (body.get("nombre") or sub.nombre).strip()
    if "categoria_id" in body:
        try:
            sub.categoria = Categoria.objects.get(pk=body["categoria_id"])
        except Categoria.DoesNotExist:
            pass
    sub.save()
    return JsonResponse({"ok": True, "subcategoria": {"id": sub.id, "nombre": sub.nombre, "categoria_id": sub.categoria_id}})
