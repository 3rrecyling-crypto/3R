"""Endpoint del asistente 3D: POST /api/yard-sketch/generar/

Recibe el pedido del cliente en lenguaje natural y devuelve un PLAN JSON que el
modelador 3D dibuja. Requiere autenticación. NO importa ni consulta facturación
(ni ningún otro módulo de negocio): la IA solo conoce el catálogo del modelador.
"""
from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from ia_studio.ia_client import IAError, resolver_config_ia
from .services import _PlanError, editar_sketch, generar_sketch


def _empresas_usuario_ids(user) -> set:
    # 3r no tiene el modelo Empresa: la IA usa las llaves de entorno del backend.
    return set()


class GenerarSketchView(APIView):
    """POST /api/yard-sketch/generar/  → { ok, plan } | { detail }"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        pedido = (data.get("pedido") or data.get("prompt") or "").strip()

        # Fotos opcionales (visión de Claude): lista de data URLs base64.
        imagenes = data.get("imagenes") or data.get("fotos") or []
        if not isinstance(imagenes, list):
            imagenes = []

        # Se acepta pedido de texto O al menos una foto. Si solo hay foto, se
        # usa un pedido por defecto para que la IA recree lo que ve.
        if not pedido and not imagenes:
            return Response({"detail": "Describe qué quieres diseñar (p. ej. '3 camiones, una nave y oficinas') o sube una foto."}, status=400)
        if not pedido:
            pedido = "Recrea en 3D el patio/instalación de la(s) foto(s) adjunta(s)."

        objetos = data.get("objetos") or []
        if not isinstance(objetos, list):
            objetos = []

        # Empresa (para leer su config de IA), validada contra las del usuario.
        empresa_id = data.get("empresa")
        try:
            empresa_id = int(empresa_id) if empresa_id else None
        except (TypeError, ValueError):
            empresa_id = None
        if empresa_id and empresa_id not in _empresas_usuario_ids(request.user):
            empresa_id = None  # no es del usuario → cae a variables de entorno

        cfg = resolver_config_ia(empresa_id)
        if not cfg["api_key"]:
            return Response(
                {"detail": "Falta configurar la API key de IA. Pide al administrador que ponga "
                           "ANTHROPIC_API_KEY (o DEEPSEEK_API_KEY) en el .env del backend."},
                status=400,
            )

        try:
            plan = generar_sketch(pedido, objetos, cfg, imagenes=imagenes)
        except _PlanError as e:
            return Response({"detail": str(e)}, status=422)
        except IAError as e:
            return Response({"detail": f"No se pudo generar el diseño: {e}"}, status=502)
        except Exception as e:  # noqa: BLE001 — mensaje legible ante cualquier fallo
            return Response({"detail": f"Error inesperado del asistente: {e}"}, status=500)

        return Response({"ok": True, "plan": plan, "proveedor": cfg["proveedor"]})


class EditarSketchView(APIView):
    """POST /api/yard-sketch/editar/  → { ok, ops, resumen } | { detail }

    Edita la escena EXISTENTE por instrucción (mueve/borra/pinta/duplica/agrega)
    devolviendo ops sobre los ids que manda el frontend. Mismo aislamiento que
    generar: la IA solo conoce el catálogo del modelador.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        instruccion = (data.get("instruccion") or data.get("pedido") or "").strip()
        imagenes = data.get("imagenes") or data.get("fotos") or []
        if not isinstance(imagenes, list):
            imagenes = []
        if not instruccion and not imagenes:
            return Response({"detail": "Escribe qué cambio quieres hacer en la escena."}, status=400)
        if not instruccion:
            instruccion = "Aplica a la escena lo que muestran la(s) foto(s) adjunta(s)."

        objetos = data.get("objetos") or []
        if not isinstance(objetos, list):
            objetos = []
        if not objetos:
            return Response({"detail": "La escena está vacía: usa el asistente para GENERAR primero."}, status=400)

        empresa_id = data.get("empresa")
        try:
            empresa_id = int(empresa_id) if empresa_id else None
        except (TypeError, ValueError):
            empresa_id = None
        if empresa_id and empresa_id not in _empresas_usuario_ids(request.user):
            empresa_id = None

        cfg = resolver_config_ia(empresa_id)
        if not cfg["api_key"]:
            return Response(
                {"detail": "Falta configurar la API key de IA. Pide al administrador que ponga "
                           "ANTHROPIC_API_KEY (o DEEPSEEK_API_KEY) en el .env del backend."},
                status=400,
            )

        try:
            res = editar_sketch(instruccion, objetos, cfg, imagenes=imagenes)
        except _PlanError as e:
            return Response({"detail": str(e)}, status=422)
        except IAError as e:
            return Response({"detail": f"No se pudo editar la escena: {e}"}, status=502)
        except Exception as e:  # noqa: BLE001
            return Response({"detail": f"Error inesperado del asistente: {e}"}, status=500)

        return Response({"ok": True, "ops": res["ops"], "resumen": res["resumen"], "proveedor": cfg["proveedor"]})
