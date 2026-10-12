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
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail={'code': 'agent_not_allowed', 'reason': reason}
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


async def _allowed(root: str) -> list[str] | None:
    """The agents allowed in project `root`, or None when it is not agent-limited."""
    hit = _cache.get(root)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    try:
        headers = {'Authorization': f'Bearer {GUARD_TOKEN}'} if GUARD_TOKEN else {}
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f'{RUNTIME_URL}/losus/api/guard/projects/{root}', headers=headers)
        r.raise_for_status()
        body = r.json()
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
