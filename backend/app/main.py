from __future__ import annotations

# Register lives at POST /api/auth/register.
import asyncio
import json
import os
import secrets
import time
import uuid
from io import BytesIO
from contextvars import ContextVar, copy_context
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from .agents import Orchestrator
from .blackboard import Blackboard
from .content import CHAPTERS, EVENTS, SONGS, find_song
from .cognition import analyze_transcript, build_series, build_trend
from .auth import (
    check_password,
    hash_password,
    new_token,
    parse_bearer,
    password_needs_upgrade,
)
from .db import init_db
from .evalset import run_eval
from .life import LESSONS, news_lines, weather_line
from .media import subtitle_timeline, to_webvtt
from .model_services import (
    analyze_acoustics,
    analyze_photo,
    download_video,
    estimate_cognitive_risk,
    poll_memory_video,
    service_status,
    submit_memory_video,
    synthesize_personal_voice,
    transcribe_audio,
    service_is_local,
)
from .llm import (
    bind_cloud_processing,
    deepseek_enabled,
    llm_enabled,
    reset_cloud_processing,
    stream_deepseek,
    uses_local_model,
)
from .page_command import PAGES, resolve as resolve_page_command
from .paint import generate_image, paint_status, style_meta

DATA_DIR = Path(
    os.getenv("NUANBAN_DATA_DIR") or (Path(__file__).resolve().parent.parent / "data")
).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PAINT_DIR = DATA_DIR / "paintings"
PAINT_DIR.mkdir(parents=True, exist_ok=True)
VOICE_DIR = DATA_DIR / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR = DATA_DIR / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_DIR = DATA_DIR / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
SESSION_COOKIE = "nuanban_session"
_REQUEST_ACCOUNT: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "nuanban_request_account", default=None
)

app = FastAPI(title="暖伴第四阶段")  # 含作画接口
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8002",
        "http://localhost:8002",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

board = Blackboard()
init_db(board.conn)
orchestrator = Orchestrator(board)

_STREAM_END = object()


def _next_stream_item(iterator):
    """Advance a blocking iterator without leaking StopIteration into asyncio."""
    try:
        return next(iterator)
    except StopIteration:
        return _STREAM_END


async def _iterate_blocking(iterator):
    """Run every blocking model step with the current request context copied in."""
    loop = asyncio.get_running_loop()
    while True:
        context = copy_context()
        item = await loop.run_in_executor(None, context.run, _next_stream_item, iterator)
        if item is _STREAM_END:
            return
        yield item


class ProfileIn(BaseModel):
    display_name: Optional[str] = None
    courtesy: Optional[str] = None
    hometown: Optional[str] = None
    birth_decade: Optional[str] = None
    speech_rate: Optional[float] = None


class PersonIn(BaseModel):
    relation: str
    name: str
    note: str = ""


class FactIn(BaseModel):
    key: str
    value: str


class ChatIn(BaseModel):
    text: str


class PageCommandIn(BaseModel):
    page: str
    text: str


class PlayIn(BaseModel):
    song_id: str


class EraIn(BaseModel):
    year: int


class RememberIn(BaseModel):
    text: str
    chapter_key: str = ""
    photo_id: int = 0


class GameIn(BaseModel):
    game: str
    score: str


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str
    role: str
    elder_username: str = ""
    link_code: str = ""


class MoodIn(BaseModel):
    mood: str


class ConsentIn(BaseModel):
    share: bool


class ConsentScopeIn(BaseModel):
    scope: str
    allowed: bool


class ReminderIn(BaseModel):
    kind: str = "medicine"
    title: str
    note: str = ""


class PaintIn(BaseModel):
    prompt: str
    style: str = "water"
    from_name: str = ""
    dedication: str = ""


class FamilyNoteIn(BaseModel):
    text: str


class MemoryProjectIn(BaseModel):
    photo_id: int = 0
    song_id: str = ""
    narration: str
    title: str = ""


class GardenStateIn(BaseModel):
    flowers: List[bool]


class PreferenceIn(BaseModel):
    key: str
    value: Any


class SpeechSynthesisIn(BaseModel):
    text: str


def account_from_header(authorization: Optional[str] = None) -> Optional[Dict[str, Any]]:
    token = parse_bearer(authorization)
    if token:
        return board.get_session(token)
    return _REQUEST_ACCOUNT.get()


def require_account(authorization: Optional[str] = None) -> Dict[str, Any]:
    account = account_from_header(authorization)
    if not account:
        raise HTTPException(401, "请先登录")
    return account


def require_family(authorization: Optional[str] = None) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") != "family":
        raise HTTPException(403, "这页是给家人看的")
    return account


def require_elder(authorization: Optional[str] = None) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "只有老人本人可以进行这项操作")
    return account


def require_elder_or_family_scope(scope: str) -> Dict[str, Any]:
    account = require_account()
    if account.get("role") == "elder":
        return account
    if account.get("role") == "family" and board.consent_scopes().get(scope):
        return account
    raise HTTPException(403, "老人尚未授权家人进行这项操作")


_LOGIN_FAILURES: Dict[str, List[float]] = {}


def _login_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return "%s:%s" % (host, username.strip().lower())


def _check_login_rate(request: Request, username: str) -> str:
    key = _login_key(request, username)
    now = time.time()
    recent = [stamp for stamp in _LOGIN_FAILURES.get(key, []) if now - stamp < 900]
    _LOGIN_FAILURES[key] = recent
    if len(recent) >= 8:
        raise HTTPException(429, "尝试次数过多，请十五分钟后再试")
    return key


def _record_login_failure(key: str) -> None:
    _LOGIN_FAILURES.setdefault(key, []).append(time.time())


def record_language_trend(text: str, source: str) -> Optional[Dict[str, Any]]:
    if not board.consent_scopes().get("transcript_analysis"):
        return None
    features = analyze_transcript(text)
    if features["char_count"] < 4:
        return None
    board.add_language_sample(text, features, source)
    trend = build_trend(board.list_cognitive_daily_metrics())
    if trend["level"] == "attention":
        board.set_kv("next_priority", "healing_song")
        board.ensure_cognitive_alert(
            "attention",
            "近期语言表现有持续变化",
            "建议陪伴熟悉的回忆训练并继续观察；这不是疾病诊断。",
        )
    return trend


def cognition_report() -> Dict[str, Any]:
    samples = board.list_cognitive_daily_metrics()
    trend = build_trend(samples)
    trend["voice"] = board.voice_summary()
    trend["series"] = build_series(samples)
    if board.consent_scopes().get("research_cognition_model"):
        try:
            research = estimate_cognitive_risk(samples, trend["voice"])
            if research:
                trend["research_model"] = research
        except Exception as exc:
            print("研究型认知模型暂时不可用：", exc)
    return trend


@app.middleware("http")
async def bind_account_memory(request: Request, call_next):
    """Bind every request to the elder selected by the signed-in account."""
    token_text = parse_bearer(request.headers.get("authorization")) or request.cookies.get(SESSION_COOKIE)
    account = board.get_session(token_text) if token_text else None
    context_token = board.bind_user((account or {}).get("linked_user_id") or "default")
    account_token = _REQUEST_ACCOUNT.set(account)
    cloud_token = bind_cloud_processing(
        bool(account) and board.consent_scopes().get("cloud_conversation", False)
    )
    try:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.cookies.get(SESSION_COOKIE):
            origin = (request.headers.get("origin") or "").rstrip("/")
            expected = ("%s://%s" % (request.url.scheme, request.headers.get("host", ""))).rstrip("/")
            if origin and origin != expected:
                return JSONResponse({"detail": "请求来源不受信任"}, status_code=403)
        public_api = request.url.path in ("/api/health", "/api/auth/login", "/api/auth/register", "/api/auth/logout")
        if request.method != "OPTIONS" and request.url.path.startswith("/api/") and not public_api and not account:
            return JSONResponse({"detail": "请先登录"}, status_code=401)
        return await call_next(request)
    finally:
        reset_cloud_processing(cloud_token)
        _REQUEST_ACCOUNT.reset(account_token)
        board.reset_user(context_token)


@app.get("/api/health")
def health() -> Dict[str, str]:
    if uses_local_model() and llm_enabled():
        llm = "local-1.5b"
        try:
            import httpx as _httpx

            probe = _httpx.get(
                "http://127.0.0.1:8001/health",
                timeout=2.0,
                trust_env=False,
            )
            if probe.status_code != 200:
                llm = "local-1.5b-down"
        except Exception:
            llm = "local-1.5b-down"
    elif llm_enabled():
        llm = "cloud"
    else:
        llm = "rules"
    return {
        "status": "ok",
        "stage": "4",
        "llm": llm,
        "deepseek": "on" if deepseek_enabled() else "off",
        "paint": "on" if paint_status().get("enabled") else "off",
    }


@app.get("/api/models/status")
def models_status(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    require_account(authorization)
    services = service_status()
    scopes = board.consent_scopes()
    original_available = False
    if uses_local_model() and llm_enabled():
        try:
            import httpx as _httpx

            original_available = _httpx.get(
                "http://127.0.0.1:8001/health", timeout=2.0, trust_env=False
            ).status_code == 200
        except Exception:
            original_available = False
    paint = paint_status()
    services["original_chat"] = {
        "enabled": uses_local_model() and llm_enabled(),
        "available": original_available,
        "active": original_available,
        "model": os.getenv("LLM_MODEL", "nuanban"),
    }
    services["deepseek"] = {
        "enabled": deepseek_enabled(),
        "available": deepseek_enabled(),
        "active": deepseek_enabled() and bool(scopes.get("cloud_conversation")),
        "allowed": bool(scopes.get("cloud_conversation")),
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
    }
    services["paint"] = {
        **paint,
        "available": bool(paint.get("enabled")),
        "active": bool(paint.get("enabled")),
        "direct_request": True,
    }
    return {"services": services}


@app.post("/api/auth/login")
def login(payload: LoginIn, request: Request, response: Response) -> Dict[str, Any]:
    rate_key = _check_login_rate(request, payload.username)
    account = board.find_account(payload.username)
    if not account or not check_password(payload.password, account.get("password_hash") or ""):
        _record_login_failure(rate_key)
        raise HTTPException(401, "账号或口令不正确")
    _LOGIN_FAILURES.pop(rate_key, None)
    if password_needs_upgrade(account.get("password_hash") or ""):
        board.update_password_hash(int(account["id"]), hash_password(payload.password))
    token = new_token()
    board.create_session(int(account["id"]), token)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=request.url.scheme == "https" or os.getenv("COOKIE_SECURE", "") == "1",
        samesite="lax",
        path="/",
    )
    return {
        "role": account["role"],
        "display_name": account["display_name"],
        "username": account["username"],
    }


@app.post("/api/auth/register")
def register(payload: RegisterIn) -> Dict[str, Any]:
    role = (payload.role or "").strip()
    if role not in ("elder", "family"):
        raise HTTPException(400, "请先选老人或家人")
    username = (payload.username or "").strip()
    if len(username) < 2:
        raise HTTPException(400, "账号至少两个字")
    if len(payload.password or "") < 8:
        raise HTTPException(400, "口令至少 8 位")
    if board.find_account(username):
        raise HTTPException(400, "这个账号已经有人用了，换一个吧")
    if role == "elder":
        linked_user_id = "elder-" + uuid.uuid4().hex
    else:
        elder = board.find_account((payload.elder_username or "").strip())
        if not elder or elder.get("role") != "elder":
            raise HTTPException(400, "请填写已经注册的老人账号，家人才能看到对应内容")
        expected_code = str(elder.get("family_link_code") or "")
        if not expected_code or not secrets.compare_digest(
            expected_code, (payload.link_code or "").strip()
        ):
            raise HTTPException(400, "老人提供的六位关联码不正确")
        linked_user_id = elder.get("linked_user_id") or ""
    acc = board.create_account(
        username=username,
        password_hash=hash_password(payload.password),
        role=role,
        display_name=username,
        linked_user_id=linked_user_id,
    )
    if role == "elder":
        board.ensure_user(linked_user_id, username)
    return {
        "ok": True,
        "role": acc["role"],
        "display_name": acc["display_name"],
        "username": acc["username"],
        "message": "注册成功，请登录",
    }


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, authorization: Optional[str] = Header(None)) -> Dict[str, bool]:
    token = parse_bearer(authorization) or request.cookies.get(SESSION_COOKIE)
    if token:
        board.delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    return {"ok": True}


@app.get("/api/auth/me")
def me(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_account(authorization)
    return {
        "role": account["role"],
        "display_name": account["display_name"],
        "username": account["username"],
    }


@app.get("/api/family/link-code")
def get_family_link_code(authorization: Optional[str] = Header(None)) -> Dict[str, str]:
    account = require_elder(authorization)
    code = board.family_link_code(int(account["id"]))
    if not code:
        code = board.rotate_family_link_code(int(account["id"]))
    return {"link_code": code}


@app.post("/api/family/link-code/rotate")
def rotate_family_link_code(authorization: Optional[str] = Header(None)) -> Dict[str, str]:
    account = require_elder(authorization)
    return {"link_code": board.rotate_family_link_code(int(account["id"]))}


@app.get("/api/session")
def session() -> Dict[str, Any]:
    require_elder()
    data = board.snapshot()
    greet = orchestrator.greeting()
    data["greeting"] = greet["greeting"]
    data["songs"] = SONGS
    data["events"] = EVENTS
    data["chapter_meta"] = CHAPTERS
    data["consent"] = board.share_digest()
    data["consent_scopes"] = board.consent_scopes()
    data["today_mood"] = (board.get_today_mood() or {}).get("mood") or ""
    data["week_moods"] = board.list_moods(board.week_start())
    data["unused_days"] = board.unused_days()
    data["digest_preview"] = orchestrator.guardian.weekly_digest(board)
    return data


@app.put("/api/profile")
def update_profile(payload: ProfileIn) -> Dict[str, Any]:
    require_elder_or_family_scope("family_care_edit")
    return board.update_profile(payload.dict(exclude_none=True))


@app.post("/api/people")
def add_person(payload: PersonIn) -> Dict[str, Any]:
    require_elder_or_family_scope("family_care_edit")
    if not payload.relation.strip() or not payload.name.strip():
        raise HTTPException(400, "请写下称呼和名字")
    return board.add_person(payload.relation.strip(), payload.name.strip(), payload.note.strip())


@app.delete("/api/people/{person_id}")
def delete_person(person_id: int) -> Dict[str, bool]:
    require_elder_or_family_scope("family_care_edit")
    board.delete_person(person_id)
    return {"ok": True}


def _image_suffix(file: UploadFile) -> str:
    suffix = Path(file.filename or "photo.jpg").suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(400, "请上传 JPG、PNG 或 WebP 图片")
    return suffix


async def _read_verified_image(file: UploadFile, limit: int) -> tuple[str, bytes]:
    """Read a bounded upload and verify its real image format."""
    declared_suffix = _image_suffix(file)
    chunks: List[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(400, "图片过大，请压缩后再上传")
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        raise HTTPException(400, "图片为空")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
            actual_format = (image.format or "").upper()
    except Exception as exc:
        raise HTTPException(400, "文件不是有效的图片") from exc
    suffixes = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
    suffix = suffixes.get(actual_format)
    if not suffix:
        raise HTTPException(400, "只支持 JPG、PNG 或 WebP 图片")
    if declared_suffix == ".jpeg" and suffix == ".jpg":
        return suffix, content
    return suffix, content


async def _save_avatar(file: UploadFile) -> str:
    suffix, content = await _read_verified_image(file, 8 * 1024 * 1024)
    name = uuid.uuid4().hex + suffix
    (AVATAR_DIR / name).write_bytes(content)
    return name


@app.post("/api/profile/photo")
async def upload_profile_photo(file: UploadFile = File(...)) -> Dict[str, Any]:
    require_elder_or_family_scope("family_care_edit")
    saved = board.set_profile_photo(await _save_avatar(file))
    saved["photo_url"] = "/api/avatars/%s" % saved.get("photo")
    return saved


@app.post("/api/people/{person_id}/photo")
async def upload_person_photo(person_id: int, file: UploadFile = File(...)) -> Dict[str, Any]:
    require_elder_or_family_scope("family_care_edit")
    saved = board.set_person_photo(person_id, await _save_avatar(file))
    if not saved:
        raise HTTPException(404, "没有找到这位家人")
    saved["photo_url"] = "/api/avatars/%s" % saved.get("photo")
    return saved


@app.get("/api/avatars/{name}")
def get_avatar(name: str) -> FileResponse:
    require_account()
    safe = Path(name).name
    path = AVATAR_DIR / safe
    if safe != name or not board.owns_avatar_file(safe) or not path.exists():
        raise HTTPException(404, "没有这张头像")
    return FileResponse(str(path), headers={"X-Content-Type-Options": "nosniff"})


@app.get("/api/preferences")
def preferences() -> Dict[str, Any]:
    require_account()
    raw_volume = board.get_kv("preference.audio_volume")
    try:
        volume = min(1.0, max(0.0, float(raw_volume)))
    except (TypeError, ValueError):
        volume = 0.9
    return {"audio_volume": volume}


@app.put("/api/preferences")
def update_preference(payload: PreferenceIn) -> Dict[str, Any]:
    require_account()
    if payload.key != "audio_volume":
        raise HTTPException(400, "没有这个界面偏好")
    try:
        value = min(1.0, max(0.0, float(payload.value)))
    except (TypeError, ValueError):
        raise HTTPException(400, "音量设置不正确")
    board.set_kv("preference.audio_volume", str(value))
    return {"key": payload.key, "value": value}


@app.put("/api/facts/{fact_id}")
def update_fact(fact_id: int, payload: FactIn, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "只有老人本人可以修改个人记忆")
    if not payload.key.strip() or not payload.value.strip():
        raise HTTPException(400, "记忆类别和内容不能为空")
    saved = board.update_fact(fact_id, payload.key, payload.value)
    if not saved:
        raise HTTPException(404, "没有找到这条记忆")
    return saved


@app.delete("/api/facts/{fact_id}")
def delete_fact(fact_id: int, authorization: Optional[str] = Header(None)) -> Dict[str, bool]:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "只有老人本人可以删除个人记忆")
    board.delete_fact(fact_id)
    return {"ok": True}


@app.get("/api/traces")
def traces() -> Dict[str, Any]:
    require_elder()
    return {"traces": board.recent_traces(12)}


@app.post("/api/page-command")
def page_command(payload: PageCommandIn) -> Dict[str, Any]:
    require_elder()
    return resolve_page_command(payload.page, payload.text)


@app.post("/api/page-talk")
def page_talk(payload: PageCommandIn, authorization: Optional[str] = Header(None)) -> StreamingResponse:
    account = require_elder(authorization)
    linked_user_id = account.get("linked_user_id") or "default"
    title = (PAGES.get(payload.page) or {}).get("title") or "暖伴"

    async def event_stream():
        context_token = board.bind_user(linked_user_id)
        cloud_allowed = board.consent_scopes().get("cloud_conversation", False)
        cloud_token = bind_cloud_processing(cloud_allowed)
        try:
            record_language_trend(payload.text, payload.page or "page")
            if deepseek_enabled() and cloud_allowed:
                emitted = False
                try:
                    async for token in _iterate_blocking(stream_deepseek(title, payload.text)):
                        emitted = True
                        yield "data: %s\n\n" % json.dumps(
                            {"type": "token", "text": token, "model": "deepseek"}, ensure_ascii=False
                        )
                    if emitted:
                        yield "data: %s\n\n" % json.dumps(
                            {"type": "done", "page": payload.page, "page_title": title, "model": "deepseek"},
                            ensure_ascii=False,
                        )
                        return
                except Exception:
                    if emitted:
                        raise
                    print("DeepSeek 页面闲聊不可用，改用原训练模型")
            async for event in _iterate_blocking(orchestrator.handle_user(payload.text)):
                if event.get("type") == "route":
                    event["page"] = payload.page
                    event["page_title"] = title
                yield "data: %s\n\n" % json.dumps(event, ensure_ascii=False)
        except Exception as exc:
            yield "data: %s\n\n" % json.dumps(
                {"type": "error", "message": "暖伴这会儿接不上话，请再试一次"},
                ensure_ascii=False,
            )
            print("DeepSeek 页面对话失败：", exc)
        finally:
            reset_cloud_processing(cloud_token)
            board.reset_user(context_token)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/chat")
def chat(payload: ChatIn, authorization: Optional[str] = Header(None)) -> StreamingResponse:
    account = require_elder(authorization)
    linked_user_id = account.get("linked_user_id") or "default"

    async def event_stream():
        context_token = board.bind_user(linked_user_id)
        cloud_token = bind_cloud_processing(board.consent_scopes().get("cloud_conversation", False))
        try:
            record_language_trend(payload.text, "talk")
            async for event in _iterate_blocking(orchestrator.handle_user(payload.text)):
                yield "data: %s\n\n" % json.dumps(event, ensure_ascii=False)
        finally:
            reset_cloud_processing(cloud_token)
            board.reset_user(context_token)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/heal/play")
def heal_play(payload: PlayIn) -> Dict[str, Any]:
    require_elder()
    if not find_song(payload.song_id):
        raise HTTPException(404, "没有这首歌")
    return orchestrator.play_song(payload.song_id)


@app.post("/api/heal/era")
def heal_era(payload: EraIn) -> Dict[str, Any]:
    require_elder()
    memory = orchestrator.memory.retrieve(board)
    result = orchestrator.healing.era(payload.year, memory)
    board.set_kv("last_era", str(payload.year))
    board.add_message("assistant", result["speak"])
    trace = board.add_trace("healing", "年代讲述", [])
    result["trace"] = trace
    result["route"] = "healing"
    return result


@app.post("/api/heal/remember")
def heal_remember(payload: RememberIn) -> Dict[str, Any]:
    require_elder()
    return orchestrator.remember_text(payload.text, payload.chapter_key, payload.photo_id)


@app.delete("/api/chapters/{chapter_key}")
def clear_chapter(chapter_key: str, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "只有老人本人可以重写回忆录")
    if chapter_key not in {item["key"] for item in CHAPTERS}:
        raise HTTPException(404, "没有这一章")
    return board.clear_chapter(chapter_key)


@app.post("/api/heal/game")
def heal_game(payload: GameIn) -> Dict[str, Any]:
    require_elder()
    memory = orchestrator.memory.retrieve(board)
    speak = orchestrator.healing.encourage(payload.game, payload.score, memory)
    board.add_message("assistant", speak)
    board.add_trace("healing", "游戏结束鼓励", [])
    return {"speak": speak, "route": "healing"}


@app.post("/api/mood")
def set_mood(payload: MoodIn) -> Dict[str, Any]:
    require_elder()
    if payload.mood not in ("sunny", "calm", "low"):
        raise HTTPException(400, "请点晴、平或阴")
    saved = board.set_mood(payload.mood, "garden")
    if payload.mood == "low":
        board.set_kv("next_priority", "healing_song")
        speak = "记下了。不做诊断。想听一首老歌，跟我说一声就好。"
    elif payload.mood == "sunny":
        speak = "今天是晴的。花园里又多开了一朵。"
    else:
        speak = "平平的一天也很好。花还在慢慢长。"
    board.add_trace("guardian", "老人在花园点了心情", [{"type": "mood", "value": payload.mood}])
    return {
        "mood": saved,
        "speak": speak,
        "week_moods": board.list_moods(board.week_start()),
        "digest_preview": orchestrator.guardian.weekly_digest(board),
    }


@app.post("/api/consent")
def set_consent(payload: ConsentIn) -> Dict[str, Any]:
    require_elder()
    board.set_share_digest(payload.share)
    board.set_consent_scope("family_digest", payload.share)
    return {
        "consent": board.share_digest(),
        "digest_preview": orchestrator.guardian.weekly_digest(board),
    }


@app.get("/api/consent/scopes")
def get_consent_scopes(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    require_elder(authorization)
    return {"scopes": board.consent_scopes()}


@app.put("/api/consent/scopes")
def update_consent_scope(payload: ConsentScopeIn, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "只有老人本人可以修改这些授权")
    try:
        scopes = board.set_consent_scope(payload.scope, payload.allowed)
    except ValueError:
        raise HTTPException(400, "没有这个授权项目")
    return {"scopes": scopes}


@app.get("/api/cognition/trends")
def cognition_trends(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_account(authorization)
    scopes = board.consent_scopes()
    if account.get("role") == "family" and not scopes.get("family_cognition"):
        return {
            "shared": False,
            "trend": None,
            "message": "老人尚未授权家人查看语言趋势。",
        }
    return {
        "shared": True,
        "trend": cognition_report(),
        "alerts": board.list_cognitive_alerts(),
    }


@app.post("/api/cognition/alerts/{alert_id}/ack")
def acknowledge_cognition_alert(alert_id: int, authorization: Optional[str] = Header(None)) -> Dict[str, bool]:
    require_family(authorization)
    board.acknowledge_cognitive_alert(alert_id)
    return {"ok": True}


@app.get("/api/memory-projects")
def memory_projects(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "记忆作品只在老人本人页面播放")
    items = board.list_memory_projects()
    for index, item in enumerate(items[:3]):
        remote_video = str(item.get("video_url") or "").startswith(("http://", "https://"))
        if item.get("video_job_id") and (not item.get("video_url") or remote_video) and item.get("status") not in ("failed", "canceled"):
            try:
                result = poll_memory_video(str(item["video_job_id"]))
                if result and result.get("video_url") and result.get("status") == "succeeded":
                    filename = uuid.uuid4().hex + ".mp4"
                    if download_video(result["video_url"], VIDEO_DIR / filename):
                        result["video_url"] = "/api/memory-videos/" + filename
                if result:
                    items[index] = board.set_memory_project_video(int(item["id"]), result)
            except Exception as exc:
                print("查询记忆影像状态失败：", exc)
    for item in items:
        item["photo_url"] = "/api/uploads/%s" % item["photo_filename"] if item.get("photo_filename") else ""
        item["voice_url"] = "/api/voice/%s" % item["voice_session_id"] if item.get("voice_session_id") else ""
        voice = board.get_voice_session(int(item.get("voice_session_id") or 0)) if item.get("voice_session_id") else None
        duration_ms = int((voice or {}).get("duration_ms") or max(3000, len(item.get("narration") or "") * 220))
        item["duration_ms"] = duration_ms
        item["subtitles"] = subtitle_timeline(item.get("narration") or "", duration_ms)
        item["subtitle_url"] = "/api/memory-projects/%s/subtitles.vtt" % item["id"]
    return {"projects": items}


@app.get("/api/memory-videos/{name}")
def get_memory_video(name: str, authorization: Optional[str] = Header(None)) -> FileResponse:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "记忆影像只允许老人本人播放")
    safe_name = Path(name).name
    path = VIDEO_DIR / safe_name
    if safe_name != name or not board.owns_memory_video("/api/memory-videos/" + safe_name) or not path.exists():
        raise HTTPException(404, "没有这个记忆影像")
    return FileResponse(str(path), media_type="video/mp4")


@app.get("/api/memory-projects/{project_id}/subtitles.vtt")
def memory_project_subtitles(project_id: int, authorization: Optional[str] = Header(None)) -> PlainTextResponse:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "记忆作品只允许老人本人读取")
    item = board.get_memory_project(project_id)
    if not item:
        raise HTTPException(404, "没有这个时光作品")
    voice = board.get_voice_session(int(item.get("voice_session_id") or 0)) if item.get("voice_session_id") else None
    duration_ms = int((voice or {}).get("duration_ms") or max(3000, len(item.get("narration") or "") * 220))
    return PlainTextResponse(to_webvtt(subtitle_timeline(item.get("narration") or "", duration_ms)), media_type="text/vtt")


@app.post("/api/memory-projects")
def create_memory_project(payload: MemoryProjectIn, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "只有老人本人可以制作记忆作品")
    if not board.consent_scopes().get("memory_video"):
        raise HTTPException(403, "请先在我的资料中允许制作记忆影像")
    if len(payload.narration.strip()) < 4:
        raise HTTPException(400, "请先讲一小段照片故事")
    try:
        item = board.add_memory_project(
            payload.photo_id, payload.song_id, payload.narration, payload.title
        )
    except ValueError:
        raise HTTPException(404, "没有找到这张照片")
    full_item = board.get_memory_project(int(item["id"])) or item
    scopes = board.consent_scopes()
    video_allowed = service_is_local("VIDEO_SERVICE_URL") or scopes.get("cloud_video_processing")
    if video_allowed and full_item.get("photo_filename"):
        photo_path = UPLOAD_DIR / str(full_item["photo_filename"])
        voice = board.get_voice_session(int(full_item.get("voice_session_id") or 0)) if full_item.get("voice_session_id") else None
        audio_path = VOICE_DIR / str(voice["filename"]) if voice else None
        try:
            submitted = submit_memory_video(photo_path, payload.narration, payload.title, audio_path)
            if submitted:
                item = board.set_memory_project_video(int(item["id"]), submitted)
        except Exception as exc:
            print("记忆影像服务暂时不可用，已保留故事板：", exc)
    item["message"] = "照片、口述与配乐已经组成一份时光故事板。"
    if item.get("video_job_id"):
        item["message"] = "时光故事板已经保存，记忆影像正在生成。"
    return item


@app.get("/api/garden")
def garden() -> Dict[str, Any]:
    require_elder()
    raw_flowers = board.get_kv("garden.flowers")
    try:
        flowers = [bool(value) for value in json.loads(raw_flowers)]
    except (TypeError, ValueError, json.JSONDecodeError):
        flowers = []
    if len(flowers) != 10:
        flowers = [False] * 10
    return {
        "today_mood": (board.get_today_mood() or {}).get("mood") or "",
        "week_moods": board.list_moods(board.week_start()),
        "consent": board.share_digest(),
        "digest_preview": orchestrator.guardian.weekly_digest(board),
        "letter": orchestrator.guardian.family_letter(board),
        "week_start": board.week_start(),
        "flowers": flowers,
    }


@app.put("/api/garden/state")
def update_garden_state(payload: GardenStateIn) -> Dict[str, Any]:
    require_elder()
    if len(payload.flowers) != 10:
        raise HTTPException(400, "花园状态不完整")
    flowers = [bool(value) for value in payload.flowers]
    board.set_kv("garden.flowers", json.dumps(flowers))
    return {"flowers": flowers}


def _family_note_out() -> Optional[Dict[str, Any]]:
    note = board.get_family_note()
    if not note.get("text"):
        return None
    return {
        "text": note.get("text") or "",
        "from_name": note.get("from_name") or "",
        "pending": not bool(note.get("delivered")),
        "created_at": note.get("created_at") or "",
    }


@app.get("/api/family/digest")
def family_digest(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_family(authorization)
    elder_name = board.get_profile().get("courtesy") or "老人"
    unused = board.unused_days()
    note = _family_note_out()
    if not board.share_digest():
        return {
            "consent": False,
            "digest": None,
            "letter": "",
            "unused_days": 0,
            "note": note,
            "elder_name": "老人",
            "viewer": account.get("display_name") or "家人",
            "message": "还没有打开周报。聊天原文本来就不会给您看。",
        }
    digest = orchestrator.guardian.weekly_digest(board)
    board.add_trace("guardian", "子女查看周报，已过滤原文", [])
    return {
        "consent": True,
        "digest": digest,
        "cognition": cognition_report()
        if board.consent_scopes().get("family_cognition")
        else None,
        "cognition_shared": board.consent_scopes().get("family_cognition", False),
        "cognition_alerts": board.list_cognitive_alerts()
        if board.consent_scopes().get("family_cognition")
        else [],
        "letter": orchestrator.guardian.family_letter(board),
        "unused_days": unused,
        "note": note,
        "elder_name": elder_name,
        "viewer": account.get("display_name") or "家人",
    }


@app.get("/api/family/care")
def family_care(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    require_family(authorization)
    if not board.consent_scopes().get("family_care_view"):
        return {
            "shared": False,
            "profile": {},
            "people": [],
            "note": _family_note_out(),
            "unused_days": 0,
            "message": "老人尚未授权家人查看照料资料。",
        }
    return {
        "shared": True,
        "editable": board.consent_scopes().get("family_care_edit", False),
        "profile": board.get_profile(),
        "people": board.list_people(),
        "note": _family_note_out(),
        "unused_days": board.unused_days(),
    }


@app.post("/api/family/note")
def save_family_note(payload: FamilyNoteIn, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_family(authorization)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "请写下要捎的那一句")
    if len(text) > 80:
        raise HTTPException(400, "请写成一句，八十个字以内")
    note = board.set_family_note(text, account.get("display_name") or "家里人")
    board.add_trace("guardian", "家人写下捎话，下次开口由暖伴转述", [])
    return {"note": _family_note_out() or note}


@app.delete("/api/family/note")
def clear_family_note(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    require_family(authorization)
    board.set_family_note("", "")
    return {"note": None}


@app.get("/api/reminders")
def list_reminders(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") == "family" and not board.consent_scopes().get("family_reminders"):
        raise HTTPException(403, "老人尚未授权家人查看提醒")
    return {"reminders": board.list_reminders()}


@app.post("/api/reminders")
def add_reminder(payload: ReminderIn, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") == "family" and not board.consent_scopes().get("family_reminders"):
        raise HTTPException(403, "老人尚未授权家人修改提醒")
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(400, "请写下提醒")
    kind = payload.kind if payload.kind in ("medicine", "visit", "other") else "other"
    return board.add_reminder(kind, title, (payload.note or "").strip())


@app.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, authorization: Optional[str] = Header(None)) -> Dict[str, bool]:
    account = require_account(authorization)
    if account.get("role") == "family" and not board.consent_scopes().get("family_reminders"):
        raise HTTPException(403, "老人尚未授权家人修改提醒")
    board.delete_reminder(reminder_id)
    return {"ok": True}


@app.get("/api/life")
def life_pack(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    require_elder(authorization)
    hometown = (board.get_profile() or {}).get("hometown") or "南通"
    lessons = []
    for key, item in LESSONS.items():
        lessons.append(
            {
                "id": key,
                "title": item["title"],
                "steps": item["steps"],
                "encourage": item["encourage"],
            }
        )
    return {
        "weather": weather_line(hometown),
        "news": news_lines(),
        "reminders": board.list_reminders(),
        "lessons": lessons,
    }


@app.get("/api/observe")
def observe(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    require_family(authorization)
    if not board.consent_scopes().get("family_cognition"):
        return {
            "shared": False,
            "observations": [],
            "traces": [],
            "message": "老人尚未授权家人查看观察摘要。",
        }
    safe_traces = [
        {
            "route": item.get("route") or "",
            "reason": item.get("reason") or "",
            "created_at": item.get("created_at") or "",
        }
        for item in board.recent_traces(24)
    ]
    return {
        "shared": True,
        "observations": [],
        "traces": safe_traces,
    }


@app.get("/api/observe/eval")
def observe_eval_get(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    require_family(authorization)
    if not board.consent_scopes().get("family_cognition"):
        raise HTTPException(403, "老人尚未授权家人查看观察评估")
    return run_eval(orchestrator)


@app.post("/api/observe/eval")
def observe_eval_post(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    require_family(authorization)
    if not board.consent_scopes().get("family_cognition"):
        raise HTTPException(403, "老人尚未授权家人查看观察评估")
    return run_eval(orchestrator)


@app.post("/api/photos")
async def upload_photo(
    file: UploadFile = File(...),
    caption: str = Form(""),
) -> Dict[str, Any]:
    require_elder()
    suffix, content = await _read_verified_image(file, 12 * 1024 * 1024)
    name = "%s%s" % (uuid.uuid4().hex, suffix)
    target = UPLOAD_DIR / name
    target.write_bytes(content)
    photo = board.add_photo(name, caption)
    scopes = board.consent_scopes()
    vision_local = service_is_local("VISION_BASE_URL")
    analysis_allowed = scopes.get("photo_analysis") and (
        vision_local or scopes.get("cloud_image_processing")
    )
    if analysis_allowed:
        try:
            analysis = analyze_photo(target, caption)
            if analysis and analysis.get("description"):
                photo = board.set_photo_analysis(
                    int(photo["id"]), analysis["description"], analysis.get("provider") or ""
                )
        except Exception as exc:
            print("照片理解服务暂时不可用，照片仍已保存：", exc)
    photo["url"] = "/api/uploads/%s" % name
    return photo


@app.post("/api/cognition/voice")
async def upload_voice_session(
    file: UploadFile = File(...),
    transcript: str = Form(""),
    duration_ms: int = Form(0),
    silence_ratio: float = Form(0),
    pause_count: int = Form(0),
    rms: float = Form(0),
    peak: float = Form(0),
    longest_pause_ms: int = Form(0),
    speech_segments: int = Form(0),
    zero_crossing_rate: float = Form(0),
    response_latency_ms: int = Form(0),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "只有老人本人的说话页可以上传录音")
    if not board.consent_scopes().get("audio_storage"):
        raise HTTPException(403, "尚未授权保存原始录音")
    content = await file.read()
    if not content or len(content) > 15 * 1024 * 1024:
        raise HTTPException(400, "录音为空或超过 15MB")
    mime_type = (file.content_type or "audio/webm").lower()
    suffix = ".ogg" if "ogg" in mime_type else ".webm"
    name = uuid.uuid4().hex + suffix
    path = VOICE_DIR / name
    path.write_bytes(content)
    final_transcript = transcript.strip()
    asr_provider = "browser"
    analysis: Dict[str, Any] = {}
    scopes = board.consent_scopes()
    if scopes.get("voice_analysis"):
        allow_cloud = scopes.get("cloud_voice_processing", False)
        try:
            recognized = transcribe_audio(path, mime_type) if (
                service_is_local("SPEECH_BASE_URL") or allow_cloud
            ) else None
            if recognized:
                final_transcript = recognized.get("text") or final_transcript
                asr_provider = recognized.get("provider") or "SenseVoice"
                analysis["speech"] = recognized
        except Exception as exc:
            print("语音识别服务暂时不可用，继续使用浏览器转写：", exc)
        try:
            acoustic = analyze_acoustics(path, mime_type) if (
                service_is_local("ACOUSTIC_BASE_URL") or allow_cloud
            ) else None
            if acoustic:
                analysis["acoustic"] = acoustic
                silence_ratio = float(acoustic.get("silence_ratio", silence_ratio))
                pause_count = int(acoustic.get("pause_count", pause_count))
                longest_pause_ms = int(acoustic.get("longest_pause_ms", longest_pause_ms))
                speech_segments = int(acoustic.get("speech_segments", speech_segments))
        except Exception as exc:
            print("声学分析服务暂时不可用，继续使用浏览器指标：", exc)
    return board.add_voice_session(
        name, final_transcript, duration_ms, mime_type,
        silence_ratio, pause_count, rms, peak,
        longest_pause_ms, speech_segments, zero_crossing_rate, response_latency_ms,
        asr_provider, analysis,
    )


@app.post("/api/speech/synthesize")
def synthesize_speech(payload: SpeechSynthesisIn, authorization: Optional[str] = Header(None)) -> Response:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "个性音色只供老人本人使用")
    scopes = board.consent_scopes()
    if not scopes.get("voice_personalization"):
        raise HTTPException(403, "请先在资料页允许个性音色")
    if not service_is_local("COSYVOICE_BASE_URL") and not scopes.get("cloud_voice_processing"):
        raise HTTPException(403, "请先在资料页允许云端语音处理")
    text = (payload.text or "").strip()
    if not text or len(text) > 300:
        raise HTTPException(400, "每次播报需要在300字以内")
    prompt = board.latest_voice_prompt()
    if not prompt:
        raise HTTPException(409, "还没有足够的本人录音作为音色样本")
    try:
        audio = synthesize_personal_voice(
            text, VOICE_DIR / str(prompt["filename"]), str(prompt.get("transcript") or "")
        )
    except Exception as exc:
        print("个性音色服务暂时不可用：", exc)
        audio = None
    if not audio:
        raise HTTPException(503, "个性音色服务尚未配置或暂时不可用")
    return Response(content=audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@app.get("/api/voice/{session_id}")
def get_voice_session(session_id: int, authorization: Optional[str] = Header(None)) -> FileResponse:
    account = require_account(authorization)
    if account.get("role") != "elder":
        raise HTTPException(403, "原始录音只允许老人本人播放")
    item = board.get_voice_session(session_id)
    if not item:
        raise HTTPException(404, "没有这段录音")
    path = VOICE_DIR / item["filename"]
    if not path.exists():
        raise HTTPException(404, "录音文件不存在")
    return FileResponse(str(path), media_type=item.get("mime_type") or "audio/webm")


@app.get("/api/uploads/{name}")
def get_upload(name: str) -> FileResponse:
    require_account()
    safe = Path(name).name
    path = UPLOAD_DIR / safe
    if safe != name or not board.owns_photo_file(safe) or not path.exists():
        raise HTTPException(404, "没有这张照片")
    return FileResponse(str(path), headers={"X-Content-Type-Options": "nosniff"})


def _painting_out(item: Dict[str, Any]) -> Dict[str, Any]:
    packed = dict(item)
    packed["url"] = "/api/paintings/%s" % item.get("filename")
    packed["style_label"] = (style_meta().get(item.get("style") or "") or {}).get("label") or ""
    packed["from_name"] = item.get("from_name") or ""
    packed["dedication"] = item.get("dedication") or ""
    return packed


@app.get("/api/paint/styles")
def paint_styles() -> Dict[str, Any]:
    return {"styles": list(style_meta().values())}


@app.get("/api/paintings")
def list_paintings() -> Dict[str, Any]:
    items = [_painting_out(item) for item in board.list_paintings()]
    return {"paintings": items}


@app.post("/api/paint")
def create_painting(
    payload: PaintIn, authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    # Clicking "开始作画" is an explicit, one-time request to send this prompt
    # to the configured image provider. Persistent consent remains required for
    # automatic photo analysis, but must not block a direct painting request.
    text = (payload.prompt or "").strip()
    if len(text) < 2:
        raise HTTPException(400, "请先说一说想画什么")
    if payload.style not in style_meta():
        raise HTTPException(400, "请选一种画法")
    from_name = (payload.from_name or "").strip()[:20]
    dedication = (payload.dedication or "").strip()[:40]
    account = account_from_header(authorization)
    if account and account.get("role") == "family":
        from_name = account.get("display_name") or "家里人"
    try:
        data, mime, provider = generate_image(text, payload.style)
        ext = ".png" if "png" in mime else ".jpg"
        name = "%s%s" % (uuid.uuid4().hex, ext)
        (PAINT_DIR / name).write_bytes(data)
        saved = board.add_painting(name, text, payload.style, provider, from_name, dedication)
        return _painting_out(saved)
    except HTTPException:
        raise
    except Exception as exc:
        print("文生图失败：", exc)
        raise HTTPException(502, "这一张还没有画出来，请再试一次")


@app.get("/api/paintings/{name}")
def get_painting(name: str) -> FileResponse:
    require_account()
    safe = Path(name).name
    path = PAINT_DIR / safe
    if safe != name or not board.owns_painting_file(safe) or not path.exists():
        raise HTTPException(404, "没有这张画")
    return FileResponse(str(path), headers={"X-Content-Type-Options": "nosniff"})


WEB_DIR = Path(__file__).resolve().parents[2] / "web"
_HTML_PAGES = {
    "/": "login.html",
    "/login": "login.html",
    "/register": "register.html",
    "/talk": "talk.html",
    "/nostalgia": "nostalgia.html",
    "/memoir": "memoir.html",
    "/garden": "garden.html",
    "/life": "life.html",
    "/paint": "paint.html",
    "/observe": "observe.html",
    "/games": "games.html",
    "/memory": "memory.html",
    "/profile": "profile.html",
    "/family": "family.html",
    "/care": "care.html",
    "/gift": "gift.html",
    "/companion": "talk.html",
}


def _send_html(name: str) -> FileResponse:
    path = WEB_DIR / name
    if not path.exists():
        raise HTTPException(404, "没有这一页")
    return FileResponse(str(path))


@app.get("/")
@app.get("/login")
@app.get("/register")
@app.get("/talk")
@app.get("/nostalgia")
@app.get("/memoir")
@app.get("/garden")
@app.get("/life")
@app.get("/paint")
@app.get("/observe")
@app.get("/games")
@app.get("/memory")
@app.get("/profile")
@app.get("/family")
@app.get("/care")
@app.get("/gift")
@app.get("/companion")
def html_page(request: Request) -> FileResponse:
    name = _HTML_PAGES.get(request.url.path)
    if not name:
        raise HTTPException(404, "没有这一页")
    return _send_html(name)


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8002, reload=False)
