"""Endpoints de los asistentes IA de Diagramas y Canvas.

POST /api/ia-studio/diagrama/  → { ok, plan }
POST /api/ia-studio/canvas/    → { ok, plan }

Requieren autenticación. NO importan facturación (ni otro módulo de negocio):
solo el catálogo del editor y el cliente de IA.
"""
from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from ia_studio.ia_client import IAError, resolver_config_ia
from .services import (
    _PlanError, chat_viaje, editar_canvas, generar_analisis_viaje, generar_canvas,
    generar_checklist, generar_diagrama, generar_guion_video, generar_imagen,
)


def _empresas_usuario_ids(user) -> set:
    # 3r no tiene el modelo Empresa de SANBENITO: sin config por empresa, la IA
    # usa las llaves de entorno del backend.
    return set()


def _empresa_id_validada(request, data: dict):
    empresa_id = data.get("empresa")
    try:
        empresa_id = int(empresa_id) if empresa_id else None
    except (TypeError, ValueError):
        empresa_id = None
    if empresa_id and empresa_id not in _empresas_usuario_ids(request.user):
        empresa_id = None
    return empresa_id


def _resolver_cfg(request, data: dict):
    """Config de IA de la empresa del usuario (validada) con fallback a entorno."""
    return resolver_config_ia(_empresa_id_validada(request, data))


def _gemini_key(request, data: dict) -> str:
    """Key de Gemini (imagen_api_key del panel Configuración → IA) con fallback a env."""
    try:
        from api.models import ConfiguracionSistema
        k = (ConfiguracionSistema.get_config().imagen_api_key or "").strip()
        if k:
            return k
    except Exception:
        pass
    import os
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("IMAGEN_API_KEY") or "").strip()


class _BaseGenerar(APIView):
    permission_classes = [permissions.IsAuthenticated]
    generador = None  # función (pedido, cfg) -> plan

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        pedido = (data.get("pedido") or data.get("prompt") or "").strip()
        # Fotos opcionales (visión de Claude): lista de data URLs base64.
        imagenes = data.get("imagenes") or data.get("fotos") or []
        if not isinstance(imagenes, list):
            imagenes = []
        if not pedido and not imagenes:
            return Response({"detail": "Describe qué quieres que genere la IA o sube una foto."}, status=400)
        if not pedido:
            pedido = "Convierte la(s) foto(s) adjunta(s) en el resultado."
        contexto = data.get("contexto") or ""
        if not isinstance(contexto, str):
            contexto = ""
        cfg = _resolver_cfg(request, data)
        gemini_key = _gemini_key(request, data)
        # Se necesita AL MENOS un motor de texto: Gemini (gratis) o Claude/DeepSeek.
        if not gemini_key and not cfg["api_key"]:
            return Response(
                {"detail": "Falta una API key de IA. Pide al administrador que configure "
                           "GEMINI_API_KEY (gratis) o ANTHROPIC_API_KEY/DEEPSEEK_API_KEY "
                           "en el .env del backend."},
                status=400,
            )
        try:
            plan = type(self).generador(pedido, cfg, imagenes, contexto=contexto, gemini_key=gemini_key)
        except _PlanError as e:
            return Response({"detail": str(e)}, status=422)
        except IAError as e:
            return Response({"detail": f"No se pudo generar: {e}"}, status=502)
        except Exception as e:  # noqa: BLE001
            return Response({"detail": f"Error inesperado del asistente: {e}"}, status=500)
        return Response({"ok": True, "plan": plan, "proveedor": cfg["proveedor"]})


class GenerarDiagramaView(_BaseGenerar):
    generador = staticmethod(generar_diagrama)


class GenerarCanvasView(_BaseGenerar):
    generador = staticmethod(generar_canvas)


class GenerarChecklistView(_BaseGenerar):
    """Asistente del constructor de checklists: describe → nombre + descripción + campos."""
    generador = staticmethod(generar_checklist)


class GenerarGuionVideoView(_BaseGenerar):
    """Guionista del editor de video: describe → títulos en pantalla con tiempos."""
    generador = staticmethod(generar_guion_video)


class GenerarAnalisisViajeView(_BaseGenerar):
    """Analista del Simulador de Viajes: resumen de simulación → observaciones."""
    generador = staticmethod(generar_analisis_viaje)


class ChatViajeView(_BaseGenerar):
    """Chat conversacional del Simulador (Claude): pregunta del usuario → respuesta."""
    generador = staticmethod(chat_viaje)


class GenerarImagenView(_BaseGenerar):
    """Generador de imágenes (Gemini): descripción → foto en dataURL."""
    generador = staticmethod(generar_imagen)


class EditarCanvasView(APIView):
    """Edición conversacional / por visión del Canvas.

    POST { instruccion, elementos: [...], imagenes?: [...], contexto?, empresa? }
      → { ok, ops: [...] }
    Las ops (update/add/delete/fondo) las aplica el editor del frontend.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        instruccion = (data.get("instruccion") or data.get("prompt") or "").strip()
        elementos = data.get("elementos") or []
        if not isinstance(elementos, list):
            elementos = []
        imagenes = data.get("imagenes") or data.get("fotos") or []
        if not isinstance(imagenes, list):
            imagenes = []
        contexto = data.get("contexto") or ""
        if not isinstance(contexto, str):
            contexto = ""

        if not instruccion and not imagenes:
            return Response({"detail": "Escribe qué cambio quieres hacer en el lienzo."}, status=400)
        if not instruccion:
            instruccion = "Mejora el diseño del lienzo (alineación, contraste, jerarquía y espaciado)."

        cfg = _resolver_cfg(request, data)
        gemini_key = _gemini_key(request, data)
        if not gemini_key and not cfg["api_key"]:
            return Response(
                {"detail": "Falta una API key de IA. Pide al administrador que configure "
                           "GEMINI_API_KEY (gratis) o ANTHROPIC_API_KEY/DEEPSEEK_API_KEY "
                           "en el .env del backend."},
                status=400,
            )
        try:
            resultado = editar_canvas(instruccion, elementos, cfg, imagenes=imagenes,
                                      contexto=contexto, gemini_key=gemini_key)
        except _PlanError as e:
            return Response({"detail": str(e)}, status=422)
        except IAError as e:
            return Response({"detail": f"No se pudo editar: {e}"}, status=502)
        except Exception as e:  # noqa: BLE001
            return Response({"detail": f"Error inesperado del asistente: {e}"}, status=500)
        return Response({"ok": True, "ops": resultado["ops"], "proveedor": cfg["proveedor"]})
