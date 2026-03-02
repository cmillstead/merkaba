import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

UPLOAD_DIR = os.path.expanduser("~/.merkaba/uploads")
CONVERSATIONS_DIR = os.path.expanduser("~/.merkaba/conversations")

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".html", ".css",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".zip", ".tar", ".gz",
}

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.get("/api/chat/sessions")
async def list_sessions():
    """List saved chat sessions."""
    if not os.path.isdir(CONVERSATIONS_DIR):
        return {"sessions": []}
    sessions = []
    for fname in sorted(os.listdir(CONVERSATIONS_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(CONVERSATIONS_DIR, fname)
        try:
            with open(fpath) as f:
                data = json.load(f)
            messages = data.get("messages", [])
            # First user message as preview
            preview = ""
            for m in messages:
                if m.get("role") == "user" and m.get("content"):
                    preview = m["content"][:80]
                    break
            sessions.append({
                "id": data.get("session_id", fname.replace(".json", "")),
                "saved_at": data.get("saved_at"),
                "message_count": len(messages),
                "preview": preview,
            })
        except (json.JSONDecodeError, OSError):
            continue
    return {"sessions": sessions}


@router.get("/api/chat/sessions/{session_id}")
async def get_session(session_id: str):
    """Load a chat session's messages."""
    if not re.match(r"^[\w\-]+$", session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    fpath = os.path.join(CONVERSATIONS_DIR, f"{session_id}.json")
    # Ensure resolved path stays within CONVERSATIONS_DIR
    if not os.path.realpath(fpath).startswith(os.path.realpath(CONVERSATIONS_DIR)):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    if not os.path.isfile(fpath):
        raise HTTPException(status_code=404, detail="Session not found")
    with open(fpath) as f:
        data = json.load(f)
    return {"session_id": session_id, "messages": data.get("messages", [])}


@router.post("/api/upload")
async def upload_file(file: UploadFile):
    """Save an uploaded file and return its path."""
    safe_filename = os.path.basename(file.filename or "file")
    ext = os.path.splitext(safe_filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' is not allowed",
        )

    chunks = []
    total = 0
    while True:
        chunk = await file.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum of {MAX_UPLOAD_SIZE} bytes",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    # Prefix with timestamp + uuid to avoid collisions
    stem = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    dest = os.path.join(UPLOAD_DIR, f"{stem}{ext}")
    with open(dest, "wb") as f:
        f.write(content)
    return {"path": dest, "filename": file.filename, "size": len(content)}


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for chat with Merkaba agent."""
    await websocket.accept()

    pool = websocket.app.state.session_pool

    # Build a unique session ID for this WebSocket connection
    from merkaba.orchestration.session import build_session_id
    session_id = build_session_id("web", uuid.uuid4().hex[:12])

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                user_message = msg.get("message", data)
                if not isinstance(user_message, str):
                    user_message = str(user_message)
            except json.JSONDecodeError:
                user_message = data

            # Send thinking indicator
            await websocket.send_json({"type": "thinking", "tool": None, "status": "processing"})

            loop = asyncio.get_event_loop()

            def on_tool_call(tool_name, arguments, result_text):
                # Push each tool event to the WebSocket immediately from the worker thread
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json({
                        "type": "thinking",
                        "tool": tool_name,
                        "status": "completed",
                    }),
                    loop,
                )

            if pool:
                # Route through SessionPool — serializes per-session, reuses Agent
                logger.debug("Submitting to pool session %s: %s", session_id, user_message[:80])
                response = await pool.submit(session_id, user_message, on_tool_call=on_tool_call)
            else:
                # Fallback for test mode (no pool configured)
                from merkaba.agent import Agent
                from merkaba.tools.base import PermissionTier

                agent = Agent()
                agent.permission_manager.auto_approve_level = PermissionTier.MODERATE
                logger.debug("Running agent with message: %s", user_message[:80])
                response = await loop.run_in_executor(
                    None,
                    lambda: agent.run(user_message, on_tool_call=on_tool_call),
                )

            logger.debug("Agent response: %s", response[:200])

            await websocket.send_json({"type": "response", "content": response})
    except WebSocketDisconnect:
        pass
