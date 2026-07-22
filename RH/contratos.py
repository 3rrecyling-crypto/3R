"""Motor de variables y render para plantillas de contrato.

Una plantilla es HTML con marcadores `{{variable}}`. Al generar el contrato de
un empleado, cada `{{variable}}` se reemplaza por el dato real del empleado /
empresa / fecha. Portado de SANBENITO y adaptado al modelo Empleado de 3r
(usa `telefono_personal`, `departamento` FK directo, `salarios` y la empresa
del M2M `empresas`). Toda la lectura de campos es defensiva (getattr).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

_MESES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fecha_corta(d) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _fecha_larga(d) -> str:
    if not d:
        return ""
    return f"{d.day} de {_MESES[d.month]} de {d.year}"


def _money(n) -> str:
    try:
        return f"${Decimal(n):,.2f}"
    except Exception:
        return ""


# Catálogo de variables disponibles (para el editor). Agrupadas.
VARIABLES_INFO = [
    {"grupo": "Empleado", "vars": [
        {"clave": "nombre_completo", "etiqueta": "Nombre completo"},
        {"clave": "nombre", "etiqueta": "Nombre(s)"},
        {"clave": "apellido", "etiqueta": "Apellidos"},
        {"clave": "numero_empleado", "etiqueta": "Número de empleado"},
        {"clave": "rfc", "etiqueta": "RFC"},
        {"clave": "curp", "etiqueta": "CURP"},
        {"clave": "nss", "etiqueta": "NSS (IMSS)"},
        {"clave": "puesto", "etiqueta": "Puesto"},
        {"clave": "departamento", "etiqueta": "Departamento"},
        {"clave": "fecha_ingreso", "etiqueta": "Fecha de ingreso (dd/mm/aaaa)"},
        {"clave": "fecha_ingreso_larga", "etiqueta": "Fecha de ingreso (larga)"},
        {"clave": "fecha_nacimiento", "etiqueta": "Fecha de nacimiento"},
        {"clave": "direccion", "etiqueta": "Domicilio del empleado"},
        {"clave": "telefono", "etiqueta": "Teléfono"},
        {"clave": "email", "etiqueta": "Correo"},
        {"clave": "estado_civil", "etiqueta": "Estado civil"},
        {"clave": "nacionalidad", "etiqueta": "Nacionalidad"},
        {"clave": "salario_diario", "etiqueta": "Salario diario"},
        {"clave": "salario_mensual", "etiqueta": "Salario mensual (aprox.)"},
    ]},
    {"grupo": "Empresa", "vars": [
        {"clave": "empresa_nombre", "etiqueta": "Nombre comercial"},
        {"clave": "empresa_razon_social", "etiqueta": "Razón social"},
        {"clave": "empresa_rfc", "etiqueta": "RFC de la empresa"},
        {"clave": "empresa_direccion", "etiqueta": "Domicilio de la empresa"},
        {"clave": "empresa_telefono", "etiqueta": "Teléfono de la empresa"},
        {"clave": "empresa_email", "etiqueta": "Correo de la empresa"},
    ]},
    {"grupo": "Fecha", "vars": [
        {"clave": "fecha_hoy", "etiqueta": "Fecha de hoy (dd/mm/aaaa)"},
        {"clave": "fecha_hoy_larga", "etiqueta": "Fecha de hoy (larga)"},
    ]},
]


def variables_de_empleado(emp) -> dict:
    """Construye el diccionario {clave: valor} para un empleado (defensivo)."""
    hoy = date.today()
    puesto = getattr(emp, "puesto", None)
    depto = getattr(emp, "departamento", None)  # 3r: FK directo en Empleado

    # Salario más reciente.
    salario_diario = Decimal("0")
    try:
        sal = emp.salarios.order_by("-fecha_efectiva").first()
        if sal:
            salario_diario = getattr(sal, "sueldo_diario", None) or Decimal("0")
    except Exception:
        pass

    # Empresa (ternium.Empresa vía M2M `empresas`), lectura defensiva.
    empresa_obj = None
    try:
        empresa_obj = emp.empresas.first()
    except Exception:
        empresa_obj = None

    def _emp(*names) -> str:
        for n in names:
            v = getattr(empresa_obj, n, None) if empresa_obj else None
            if v:
                return str(v)
        return ""

    nombre = (getattr(emp, "nombre", "") or "").strip()
    apellido = (getattr(emp, "apellido", "") or "").strip()
    ingreso = getattr(emp, "fecha_ingreso", None) or getattr(emp, "fecha_contratacion", None)

    return {
        "nombre_completo": f"{nombre} {apellido}".strip(),
        "nombre": nombre,
        "apellido": apellido,
        "numero_empleado": getattr(emp, "numero_empleado", "") or "",
        "rfc": (getattr(emp, "rfc", "") or "").upper(),
        "curp": (getattr(emp, "curp", "") or "").upper(),
        "nss": getattr(emp, "nss", "") or "",
        "puesto": (puesto.nombre if puesto else ""),
        "departamento": (depto.nombre if depto else ""),
        "fecha_ingreso": _fecha_corta(ingreso),
        "fecha_ingreso_larga": _fecha_larga(ingreso),
        "fecha_nacimiento": _fecha_corta(getattr(emp, "fecha_nacimiento", None)),
        "direccion": getattr(emp, "direccion", "") or "",
        "telefono": getattr(emp, "telefono_personal", None) or getattr(emp, "telefono", "") or "",
        "email": getattr(emp, "email", "") or "",
        "estado_civil": getattr(emp, "estado_civil", "") or "",
        "nacionalidad": getattr(emp, "nacionalidad", "") or "",
        "salario_diario": _money(salario_diario),
        "salario_mensual": _money(salario_diario * 30),
        # Empresa
        "empresa_nombre": _emp("nombre_comercial", "nombre"),
        "empresa_razon_social": _emp("razon_social", "nombre"),
        "empresa_rfc": _emp("rfc"),
        "empresa_direccion": _emp("direccion", "domicilio"),
        "empresa_telefono": _emp("telefono"),
        "empresa_email": _emp("email", "correo"),
        # Fecha
        "fecha_hoy": _fecha_corta(hoy),
        "fecha_hoy_larga": _fecha_larga(hoy),
    }


_TOKEN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render_contrato(contenido: str, variables: dict) -> str:
    """Reemplaza `{{clave}}` por su valor. Claves desconocidas se dejan tal cual."""
    def sub(m):
        return str(variables.get(m.group(1), m.group(0)))
    return _TOKEN.sub(sub, contenido or "")


def anexo_datos_empleado(emp) -> str:
    """HTML con TODOS los datos del empleado, para anexar al final del contrato
    (una página aparte). Usa el mismo motor de variables + campos de domicilio."""
    v = variables_de_empleado(emp)
    filas = [
        ("Número de empleado", v["numero_empleado"]),
        ("Nombre completo", v["nombre_completo"]),
        ("RFC", v["rfc"]), ("CURP", v["curp"]), ("NSS (IMSS)", v["nss"]),
        ("Puesto", v["puesto"]), ("Departamento", v["departamento"]),
        ("Fecha de ingreso", v["fecha_ingreso"]),
        ("Fecha de nacimiento", v["fecha_nacimiento"]),
        ("Estado civil", v["estado_civil"]), ("Nacionalidad", v["nacionalidad"]),
        ("Domicilio", v["direccion"]),
        ("Colonia", getattr(emp, "colonia", "") or ""),
        ("Ciudad", getattr(emp, "ciudad", "") or ""),
        ("Estado", getattr(emp, "estado", "") or ""),
        ("Código postal", getattr(emp, "codigo_postal", "") or ""),
        ("Teléfono", v["telefono"]), ("Correo", v["email"]),
        ("Salario diario", v["salario_diario"]),
        ("Salario mensual (aprox.)", v["salario_mensual"]),
        ("Empresa", v["empresa_nombre"]),
    ]
    filas = [(k, val) for k, val in filas if val]
    rows = "".join(
        f'<tr><td style="border:1px solid #999;padding:6px;font-weight:bold;width:40%">{k}</td>'
        f'<td style="border:1px solid #999;padding:6px">{val}</td></tr>'
        for k, val in filas
    )
    return (
        '<div style="page-break-before:always"></div>'
        '<h2 style="text-align:center;margin:14px 0">Datos del empleado</h2>'
        f'<table style="width:100%;border-collapse:collapse;font-size:12pt">{rows}</table>'
    )
