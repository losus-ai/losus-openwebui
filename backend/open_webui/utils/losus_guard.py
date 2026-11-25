"""Losus Roster: agent-limited projects, enforced on the server (ADR 0003 in losus-roster).

A project is a top-level folder. Roster's runtime keeps its allow-list of agents (upstream model ids). This file asks the
runtime, in-process callers pass the chat's *stored* folder, never one a client sent for an existing chat.

Off unless LOSUS_RUNTIME_URL is set, so a plain Open WebUI behaves as upstream. Chats outside any folder are never checked.
When the runtime cannot be reached, the last answer for that project is used; with no answer yet, the request is denied.
"""
import logging
import os
import time

import httpx
from fastapi import HTTPException, status

from open_webui.models.chats import Chats
from open_webui.models.folders import Folders

log = logging.getLogger(__name__)

RUNTIME_URL = os.environ.get('LOSUS_RUNTIME_URL', '').rstrip('/')
GUARD_TOKEN = os.environ.get('LOSUS_GUARD_TOKEN', '')
TTL = 15.0
_cache: dict[str, tuple[float, list[str] | None]] = {}


def _deny(reason: str) -> HTTPException:
    # `message` is the string the app's error helper looks for (detail.message); without it the app falls back to
    # "Server connection failed" for a policy refusal. `code` and `reason` stay for scripts and tests.
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={'code': 'agent_not_allowed', 'reason': reason, 'message': reason},
    )


async def _root(folder_id: str) -> str | None:
    """The top-level folder above `folder_id` (a project is always one)."""
    current, seen = folder_id, set()
    while current and current not in seen and len(seen) < 16:
        seen.add(current)
        folder = await Folders.get_folder_by_id(current)
        if folder is None:
            return None
        if not folder.parent_id:
            return folder.id
        current = folder.parent_id
    return None


# One long-lived client: calls reuse a connection instead of opening and resolving a fresh one each time, which on the
# Spark stalled for 1 to 3 s now and then (found 2026-11-24). One retry covers a stale or dropped connection. If both tries
# fail the caller still fails closed (the cached answer, or a denial when there is none).
_client: httpx.AsyncClient | None = None
ATTEMPTS = 2


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=4.0),
            limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=30.0),
        )
    return _client


async def _fetch(root: str) -> dict:
    headers = {'Authorization': f'Bearer {GUARD_TOKEN}'} if GUARD_TOKEN else {}
    for attempt in range(1, ATTEMPTS + 1):
        try:
            r = await _http().get(f'{RUNTIME_URL}/losus/api/guard/projects/{root}', headers=headers)
            r.raise_for_status()  # an HTTP error status is an answer, not a transport fault: it is not retried
            return r.json()
        except httpx.TransportError as exc:
            log.warning('losus guard: runtime call %d of %d failed (%s)', attempt, ATTEMPTS, type(exc).__name__)
            if attempt == ATTEMPTS:
                raise
    raise AssertionError('unreachable')


async def _allowed(root: str) -> list[str] | None:
    """The agents allowed in project `root`, or None when it is not agent-limited."""
    hit = _cache.get(root)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    try:
        body = await _fetch(root)
        agents = list(body.get('agents') or []) if body.get('limited') else None
    except Exception as exc:
        log.warning('losus guard: runtime unavailable (%s)', type(exc).__name__)
        if hit:
            return hit[1]  # the last answer we had
        raise _deny('The project access service is unavailable')
    _cache[root] = (time.monotonic(), agents)
    return agents


async def check(folder_id: str | None, models: list[str | None]) -> None:
    """Raise 403 `agent_not_allowed` if `folder_id` sits in an agent-limited project that does not allow every model."""
    if not RUNTIME_URL or not folder_id:
        return
    root = await _root(folder_id)
    if root is None:
        return
    agents = await _allowed(root)
    if agents is None:
        return
    for model in models:
        if model and model not in agents:
            raise _deny(f'{model} is not allowed in this project')


async def check_chat(user_id: str, chat_id: str, sent_folder_id: str | None, is_new: bool, models: list[str | None]) -> None:
    """A completion: an existing chat's own stored folder decides; a new chat uses the folder it asks for."""
    if not RUNTIME_URL:
        return
    folder_id = sent_folder_id
    if not is_new and chat_id:
        folder_id = await Chats.get_chat_folder_id(chat_id, user_id)
    await check(folder_id, models)


def _saved_messages(chat: dict) -> list[dict]:
    """Every message a save carries: the history map and the legacy list."""
    found = list(((chat.get('history') or {}).get('messages') or {}).values())
    found.extend(chat.get('messages') or [])
    return [m for m in found if isinstance(m, dict)]


def _message_models(message: dict) -> set[str]:
    """The agents a message names: its own `model` and a user message's `models` list."""
    named = set(message.get('models') or [])
    named.add(message.get('model'))
    return {m for m in named if isinstance(m, str) and m}


async def check_save(chat_id: str, folder_id: str | None, stored_chat: dict, incoming: dict) -> None:
    """A chat save (POST /chats/{id}): agents it adds must be allowed in the chat's stored project.

    Only what is new or changed is checked, so a chat that already holds a since-removed agent can still be saved."""
    if not RUNTIME_URL or not folder_id:
        return
    added = {m for m in incoming.get('models') or [] if isinstance(m, str) and m} - set(stored_chat.get('models') or [])
    stored = await Chats.get_messages_map_by_chat_id(chat_id) or {}
    for message in _saved_messages(incoming):
        added |= _message_models(message) - _message_models(stored.get(message.get('id')) or {})
    await check(folder_id, sorted(added))


# ---- Roster: ask the caller's open chat page to re-read the chat --------------------------------------------------------
# Roster appends a message to a chat on the server (for example "Task #7 is resolved"). The open page only knows what it has
# loaded, so it is told to read the chat again, which upstream's chat page already does on a `chat:reload` event, with no
# page refresh. Only the chat's owner can ask, and the event goes only to that owner's own sessions.
from fastapi import APIRouter, Depends  # noqa: E402

from open_webui.utils.auth import get_verified_user  # noqa: E402

router = APIRouter()


@router.post('/chats/{chat_id}/reload')
async def reload_chat(chat_id: str, user=Depends(get_verified_user)) -> dict:
    from open_webui.socket.main import sio

    if not await Chats.get_chat_by_id_and_user_id(chat_id, user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Chat not found')
    await sio.emit(
        'events',
        {'chat_id': chat_id, 'message_id': None, 'data': {'type': 'chat:reload'}},
        room=f'user:{user.id}',
    )
    return {'ok': True}
