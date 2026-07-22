"""Utilidades para videollamadas con LiveKit.

El backend NO transporta audio/video: solo **firma** un token (JWT) que le dice
al servidor LiveKit qué sala puede unir el usuario y con qué permisos. El video
viaja peer→SFU→peers directamente contra `LIVEKIT_URL`.

Config (en `.env`, igual que el resto de secrets):

    LIVEKIT_URL=wss://tu-proyecto.livekit.cloud
    LIVEKIT_API_KEY=APIxxxxxxxx
    LIVEKIT_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

En LiveKit Cloud las llaves salen de Project → Settings → Keys. Al migrar a
self-host en AWS solo cambian estas tres variables; el resto del código es igual.
"""
from __future__ import annotations

import os
from datetime import timedelta

# Sala de LiveKit por conversación del chat. Determinística: la misma conversación
# siempre cae en la misma sala, así todos los que "inician/uniéndose" coinciden.
ROOM_PREFIX = "conv_"

# Duración del token. La llamada puede durar más: el cliente pide token nuevo al
# reconectar. 3h cubre reuniones largas sin renovar.
TOKEN_TTL = timedelta(hours=3)


def room_name(conversation_id: int | str) -> str:
    return f"{ROOM_PREFIX}{conversation_id}"


def livekit_configurado() -> bool:
    return bool(_url() and _api_key() and _api_secret())


def _url() -> str:
    return (os.environ.get("LIVEKIT_URL") or "").strip()


def _api_key() -> str:
    return (os.environ.get("LIVEKIT_API_KEY") or "").strip()


def _api_secret() -> str:
    return (os.environ.get("LIVEKIT_API_SECRET") or "").strip()


def crear_access_token(
    *,
    room: str,
    identity: str,
    nombre: str,
    admin: bool = False,
) -> str:
    """Firma un JWT de acceso a `room` para `identity`.

    - `admin=True` (miembros del ERP): puede publicar cámara/mic/pantalla, datos,
      y silenciar/expulsar a otros (útil para el anfitrión).
    - `admin=False` (invitados externos, fase posterior): solo publicar y suscribir.
    """
    from livekit import api

    grants = api.VideoGrants(
        room=room,
        room_join=True,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,   # data channel: levantar la mano, etc.
        room_admin=admin,        # mute/expulsar
    )
    token = (
        api.AccessToken(_api_key(), _api_secret())
        .with_identity(identity)
        .with_name(nombre or identity)
        .with_grants(grants)
        .with_ttl(TOKEN_TTL)
    )
    return token.to_jwt()


def server_url() -> str:
    """URL wss del servidor LiveKit que usa el cliente para conectarse."""
    return _url()


# ── Estado de salas activas (LiveKit Server API) ────────────────────────────
# LiveKit es la fuente de verdad: al iniciar marcamos la sala con el nombre del
# creador (metadata) y luego preguntamos qué salas tienen participantes. Así el
# aviso de "llamada en curso" aparece y desaparece solo, sin webhooks ni BD.

_CACHE_KEY = "livekit:salas_activas"
_EMPTY_TIMEOUT = 90  # segundos que la sala sobrevive vacía antes de cerrarse


def _api_http_url() -> str:
    """La Server API usa http(s); el cliente usa wss. Convierte una a otra."""
    u = _url()
    if u.startswith("wss://"):
        return "https://" + u[len("wss://"):]
    if u.startswith("ws://"):
        return "http://" + u[len("ws://"):]
    return u


# Timeout total de cada request a la Server API. Sin esto, si LiveKit va lento o
# está caído, cada poll/creación podría colgar un worker de Django varios minutos.
_API_TIMEOUT_S = 6


def _lk_client():
    """Cliente de la Server API con timeout. Debe crearse dentro de un event loop."""
    import aiohttp
    from livekit import api
    return api.LiveKitAPI(
        url=_api_http_url(), api_key=_api_key(), api_secret=_api_secret(),
        timeout=aiohttp.ClientTimeout(total=_API_TIMEOUT_S),
    )


async def _crear_sala_async(room: str, metadata: str) -> None:
    from livekit import api
    lk = _lk_client()
    try:
        await lk.room.create_room(api.CreateRoomRequest(
            name=room, empty_timeout=_EMPTY_TIMEOUT, metadata=metadata or "",
        ))
    finally:
        await lk.aclose()


def crear_sala(room: str, *, creador_nombre: str = "", creador_id=None) -> None:
    """Crea la sala (idempotente) con metadata del creador. Best-effort: si falla,
    la llamada sigue funcionando (el token es lo esencial)."""
    if not livekit_configurado():
        return
    import json
    from asgiref.sync import async_to_sync
    meta = json.dumps({"creador_nombre": creador_nombre or "", "creador_id": creador_id})
    try:
        async_to_sync(_crear_sala_async)(room, meta)
    except Exception:
        pass


async def _listar_salas_async() -> list:
    from livekit import api
    lk = _lk_client()
    try:
        resp = await lk.room.list_rooms(api.ListRoomsRequest())
        return list(resp.rooms)
    finally:
        await lk.aclose()


async def _eliminar_sala_async(room: str) -> None:
    from livekit import api
    lk = _lk_client()
    try:
        await lk.room.delete_room(api.DeleteRoomRequest(room=room))
    finally:
        await lk.aclose()


def eliminar_sala(room: str) -> bool:
    """Termina la videollamada para TODOS: borra la sala en LiveKit, lo que
    desconecta a cada participante al instante. Invalida el cache de activas."""
    if not livekit_configurado():
        return False
    from asgiref.sync import async_to_sync
    from django.core.cache import cache
    try:
        async_to_sync(_eliminar_sala_async)(room)
        cache.delete(_CACHE_KEY)
        return True
    except Exception:
        return False


def salas_activas() -> dict[int, dict]:
    """{conv_id: {creador_nombre, iniciada_en(iso), num_participants}} para las
    salas `conv_*` con al menos un participante. Cacheado unos segundos para que
    el polling de varios clientes no golpee la API de LiveKit."""
    if not livekit_configurado():
        return {}
    import json
    from datetime import datetime, timezone as _tz
    from asgiref.sync import async_to_sync
    from django.core.cache import cache

    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    try:
        rooms = async_to_sync(_listar_salas_async)()
    except Exception:
        rooms = []

    out: dict[int, dict] = {}
    for r in rooms:
        name = getattr(r, "name", "") or ""
        if not name.startswith(ROOM_PREFIX) or getattr(r, "num_participants", 0) < 1:
            continue
        try:
            conv_id = int(name[len(ROOM_PREFIX):])
        except ValueError:
            continue
        meta = {}
        if getattr(r, "metadata", ""):
            try:
                meta = json.loads(r.metadata)
            except Exception:
                meta = {}
        ct = getattr(r, "creation_time", 0) or 0
        iniciada = datetime.fromtimestamp(ct, tz=_tz.utc).isoformat() if ct else None
        out[conv_id] = {
            "creador_nombre": meta.get("creador_nombre") or "",
            "iniciada_en": iniciada,
            "num_participants": int(getattr(r, "num_participants", 0)),
        }

    cache.set(_CACHE_KEY, out, 4)
    return out


# ── Grabación (LiveKit Egress → S3) ─────────────────────────────────────────
# Requiere: (1) Egress habilitado en el proyecto LiveKit, (2) un bucket S3.
# La grabación usa variables DEDICADAS `LIVEKIT_S3_*` para poder activarla SIN
# mover todo el media del ERP a S3. Si no están, cae a las AWS_* de django-storages.

def _rec_cfg(lk_var: str, aws_var: str, default: str = "") -> str:
    return (os.environ.get(lk_var) or os.environ.get(aws_var) or default).strip()


def rec_bucket() -> str:
    return _rec_cfg("LIVEKIT_S3_BUCKET", "AWS_STORAGE_BUCKET_NAME")


def rec_access() -> str:
    return _rec_cfg("LIVEKIT_S3_ACCESS_KEY", "AWS_ACCESS_KEY_ID")


def rec_secret() -> str:
    return _rec_cfg("LIVEKIT_S3_SECRET", "AWS_SECRET_ACCESS_KEY")


def rec_region() -> str:
    return _rec_cfg("LIVEKIT_S3_REGION", "AWS_S3_REGION_NAME", "us-east-1")


def rec_endpoint() -> str:
    return _rec_cfg("LIVEKIT_S3_ENDPOINT", "AWS_S3_ENDPOINT_URL")


def s3_configurado() -> bool:
    return bool(rec_bucket())


def grabacion_disponible() -> bool:
    return livekit_configurado() and s3_configurado()


def _s3_upload():
    from livekit import api
    return api.S3Upload(
        access_key=rec_access(),
        secret=rec_secret(),
        region=rec_region(),
        bucket=rec_bucket(),
        endpoint=rec_endpoint() or "",
        force_path_style=(os.environ.get("AWS_S3_ADDRESSING_STYLE", "") == "path"),
    )


def presigned_url(key: str, expires: int = 3600) -> str | None:
    """URL temporal firmada para descargar una grabación del bucket."""
    if not rec_bucket():
        return None
    try:
        import boto3
        s3 = boto3.client(
            "s3",
            aws_access_key_id=rec_access(),
            aws_secret_access_key=rec_secret(),
            region_name=rec_region(),
            endpoint_url=rec_endpoint() or None,
        )
        return s3.generate_presigned_url(
            "get_object", Params={"Bucket": rec_bucket(), "Key": key}, ExpiresIn=expires,
        )
    except Exception:
        return None


async def _iniciar_grabacion_async(room: str, filepath: str) -> str:
    from livekit import api
    lk = _lk_client()
    try:
        req = api.RoomCompositeEgressRequest(
            room_name=room,
            layout="grid",
            file_outputs=[api.EncodedFileOutput(
                file_type=api.EncodedFileType.MP4, filepath=filepath, s3=_s3_upload(),
            )],
        )
        info = await lk.egress.start_room_composite_egress(req)
        return getattr(info, "egress_id", "") or ""
    finally:
        await lk.aclose()


def iniciar_grabacion(room: str, filepath: str) -> str | None:
    """Arranca la grabación a S3. Devuelve el egress_id, o None si no se pudo
    (Egress no habilitado, S3 sin configurar, etc.)."""
    if not grabacion_disponible():
        return None
    from asgiref.sync import async_to_sync
    try:
        return async_to_sync(_iniciar_grabacion_async)(room, filepath) or None
    except Exception:
        return None


async def _detener_grabacion_async(room: str) -> int:
    from livekit import api
    lk = _lk_client()
    detenidas = 0
    try:
        resp = await lk.egress.list_egress(api.ListEgressRequest(room_name=room, active=True))
        for e in getattr(resp, "items", []) or []:
            try:
                await lk.egress.stop_egress(api.StopEgressRequest(egress_id=e.egress_id))
                detenidas += 1
            except Exception:
                pass
        return detenidas
    finally:
        await lk.aclose()


def detener_grabacion(room: str) -> int:
    """Detiene toda grabación activa de la sala. Devuelve cuántas detuvo."""
    if not livekit_configurado():
        return 0
    from asgiref.sync import async_to_sync
    try:
        return async_to_sync(_detener_grabacion_async)(room)
    except Exception:
        return 0


async def _grabando_async(room: str) -> bool:
    from livekit import api
    lk = _lk_client()
    try:
        resp = await lk.egress.list_egress(api.ListEgressRequest(room_name=room, active=True))
        return bool(getattr(resp, "items", []))
    finally:
        await lk.aclose()


def esta_grabando(room: str) -> bool:
    if not livekit_configurado():
        return False
    from asgiref.sync import async_to_sync
    try:
        return async_to_sync(_grabando_async)(room)
    except Exception:
        return False
