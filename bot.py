"""
Bot Gacha v3 — Lazos
====================
Solo personajes FEMENINOS de animes y videojuegos populares. Pool: characters.json (200 pjs, 54 series).

Reglas:
- Spawn general: cada N mensajes (por defecto 100, solo admins con /timepawn).
  Solo la imagen, sin nombre, serie ni pistas. Dura 5-10 mensajes.
  Se captura con /vinculo, la primera persona gana.
  Si se escapa, se revela nombre + serie y ya no se puede capturar.
- /transmutar <id> <id> <id>: das 3 vínculos tuyos (repetidos o no) y sale un
  personaje al azar SOLO para ti, con TTL de 10-20 mensajes. Es un spawn
  aparte: no resetea ni bloquea el spawn general, pueden coexistir.
  /vinculo da prioridad a tu transmutación si tienes una activa.
- /lazos: colección paginada por serie (A-Z), formato:
    Lycoris Recoil 3/2
    1. Chisato Nishikigi [2]
    2. Takina Inoue [1]
  Arriba: tamaño de colección "X en total (Y distintos)".
  Si tienes favorita (/atesorar), primero sale su foto en el grupo.
  Botones (diseño propio, no copia): Inicio / Anterior / Siguiente / Fin,
  Inline, Cerrar.
- Botón Inline: abre el modo inline de Telegram con la rejilla de tus
  ilustraciones, solo las ves tú, no se mandan al grupo.
  Hay que activar el modo inline en BotFather: /setinline (ver README).
  Ojo: en Telegram, ver la rejilla no manda nada; si TOCAS una foto de
  la rejilla, esa foto sí se envía al chat donde estás. Para solo ver,
  basta con mirar la rejilla y cerrarla con la X.
- /pactar: trueque entre dos personas (ver docstring de pactar()).
- /tributo <id> (respondiendo a alguien): donar. /liberar <id>: eliminar (con confirmación).
- /atesorar <id>: marcar UNA favorita (reemplaza la anterior). Sin args, muestra la actual.
- /podio: ranking. /list: series del bot y cuántos pjs tiene cada una.
- Admins: /invocar (al azar), /timepawn <n> (10-500).
  Solo el PROPIETARIO del grupo: /invocar <id> para sacar un pj concreto por ID.
  Los admins con /invocar sin ID solo sacan al azar.
- Rarezas 1-5 estrellas: ★ 40%, ★★ 30%, ★★★ 18%, ★★★★ 9%, ★★★★★ 3%.
- Sin variantes por ahora (simple para calar): un personaje = una imagen.
  El pool está preparado para añadir variantes más adelante.

Imágenes: se buscan en vivo en Jikan (MyAnimeList) y, si falla, en AniList.
No se guardan ni se venden: el arte es de sus autores/estudios.
"""

import asyncio
import json
import logging
import os
import random
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputTextMessageContent,
    Update,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("lazos-bot-v3")

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
DEFAULT_SPAWN_EVERY = int(os.getenv("SPAWN_EVERY", "100"))
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
POOL_FILE = BASE_DIR / "characters.json"

RARITY_WEIGHTS = {1: 40, 2: 30, 3: 18, 4: 9, 5: 3}
RARITY_POINTS = {1: 10, 2: 20, 3: 30, 4: 50, 5: 100}
SERIES_PER_PAGE = 4
LIST_PER_PAGE = 10
TRADE_TIMEOUT = 300  # 5 minutos para completar un trueque

try:
    POOL = json.loads(POOL_FILE.read_text(encoding="utf-8"))
except Exception as e:
    logger.warning("No se pudo leer characters.json: %s", e)
    POOL = []
BY_ID = {c["id"]: c for c in POOL}
SERIES_TOTAL = {}
for _c in POOL:
    SERIES_TOTAL[_c["series"]] = SERIES_TOTAL.get(_c["series"], 0) + 1


def stars(rarity: int) -> str:
    return "★" * int(rarity) + "☆" * (5 - int(rarity))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- Datos
_data = {"chats": {}, "users": {}, "image_cache": {}}
if DATA_FILE.exists():
    try:
        _raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(_raw, dict) and "users" in _raw and "chats" in _raw:
            _data = _raw
        else:
            (BASE_DIR / "data.v1.json").write_text(
                json.dumps(_raw, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.warning("data.json era de una versión vieja, se guardó en data.v1.json.")
    except Exception as e:
        logger.warning("No se pudo leer data.json: %s", e)


def save_data():
    try:
        DATA_FILE.write_text(json.dumps(_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("No se pudo guardar data.json: %s", e)


def chat_cfg(chat_id: int) -> dict:
    return _data.setdefault("chats", {}).setdefault(
        str(chat_id), {"spawn_every": DEFAULT_SPAWN_EVERY, "counter": 0}
    )


def user_entry(user) -> dict:
    entry = _data.setdefault("users", {}).setdefault(
        str(user.id), {"username": user.username or user.first_name, "collection": {}, "favorite": None}
    )
    entry["username"] = user.username or user.first_name
    entry.setdefault("collection", {})
    entry.setdefault("favorite", None)
    return entry


def user_stats(uid: str) -> tuple[int, int, int]:
    entry = _data.get("users", {}).get(str(uid))
    if not entry:
        return 0, 0, 0
    coll = entry.get("collection", {})
    distinct = len(coll)
    total = sum(int(v) for v in coll.values())
    points = sum(RARITY_POINTS.get(BY_ID.get(int(k), {}).get("rarity", 1), 10) * int(v)
                 for k, v in coll.items() if int(k) in BY_ID)
    return distinct, total, points


_active: dict[int, dict] = {}
_active_trans: dict[int, dict] = {}
_image_cache: dict[int, str] = {int(k): v for k, v in _data.get("image_cache", {}).items()}

# Trueques en memoria (no se guardan al reiniciar; caducan en 5 min)
_trades: dict[int, dict] = {}
_trades_by_msg: dict[int, int] = {}
_trade_counter = [0]


# ---------------------------------------------------------------- Imágenes
def _resolve_image_sync(char: dict) -> str | None:
    name = char["name"]
    try:
        resp = requests.get(
            "https://api.jikan.moe/v4/characters",
            params={"q": name, "limit": 3},
            timeout=12, headers={"User-Agent": "lazos-bot/3.0"},
        )
        resp.raise_for_status()
        items = resp.json().get("data") or []
        target = normalize(name)
        for item in items:
            c = item.get("character") or item
            img = ((c.get("images") or {}).get("jpg") or {}).get("image_url")
            if img and normalize(c.get("name", "")) == target:
                return img
        if items:
            c = items[0].get("character") or items[0]
            img = ((c.get("images") or {}).get("jpg") or {}).get("image_url")
            if img:
                return img
    except Exception as e:
        logger.warning("Jikan falló para %s: %s", name, e)
    try:
        query = """query ($search: String) {
            Character(search: $search) { name { full } image { large } gender }
        }"""
        resp = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": {"search": name}},
            timeout=12, headers={"User-Agent": "lazos-bot/3.0"},
        )
        resp.raise_for_status()
        ch = (resp.json().get("data") or {}).get("Character") or {}
        img = (ch.get("image") or {}).get("large")
        if img:
            return img
    except Exception as e:
        logger.warning("AniList falló para %s: %s", name, e)
    return None


async def resolve_image(char: dict) -> str | None:
    if char["id"] in _image_cache:
        return _image_cache[char["id"]]
    url = await asyncio.to_thread(_resolve_image_sync, char)
    if url:
        _image_cache[char["id"]] = url
        _data.setdefault("image_cache", {})[str(char["id"])] = url
        save_data()
    return url


def pick_character(exclude_ids: set[int] | None = None) -> dict:
    rarities = list(RARITY_WEIGHTS.keys())
    weights = [RARITY_WEIGHTS[r] for r in rarities]
    rarity = random.choices(rarities, weights=weights, k=1)[0]
    candidates = [c for c in POOL if c["rarity"] == rarity
                  and not (exclude_ids and c["id"] in exclude_ids)]
    if not candidates:
        candidates = [c for c in POOL if not (exclude_ids and c["id"] in exclude_ids)] or POOL
    return random.choice(candidates)


def reveal_text(char: dict) -> str:
    kind = "Anime" if char["type"] == "Anime" else "Videojuego"
    return f"{char['name']} de {char['series']} ({kind}) {stars(char['rarity'])}"


# ---------------------------------------------------------------- Spawns

async def _spawn_photo(context, chat_id: int, char: dict, caption: str) -> int | None:
    image_url = await resolve_image(char)
    if not image_url:
        return None
    try:
        msg = await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption)
        return msg.message_id
    except Exception as e:
        logger.warning("No se pudo enviar la foto (%s)", e)
        return None


async def spawn_character(context: ContextTypes.DEFAULT_TYPE, chat_id: int, char: dict | None = None) -> bool:
    """Spawn general. Si char es None, es al azar. Devuelve False si ya hay uno activo."""
    if chat_id in _active or not POOL:
        return False
    cfg = chat_cfg(chat_id)
    cfg["counter"] = 0
    for _ in range(5):
        c = char or pick_character()
        image_url = await resolve_image(c)
        if image_url:
            char = c
            break
        if char:
            return False
        char = None
    if not char:
        return False
    ttl = random.randint(5, 10)
    _active[chat_id] = {"char_id": char["id"], "ttl": ttl}
    save_data()
    msg_id = await _spawn_photo(
        context, chat_id, char,
        "✨ ¡Ha aparecido un personaje misterioso! ✨\n\nUsa /vinculo para capturarla",
    )
    if msg_id:
        _active[chat_id]["message_id"] = msg_id
    else:
        await context.bot.send_message(
            chat_id, "✨ ¡Ha aparecido un personaje misterioso! ✨\n\nUsa /vinculo para capturarla"
        )
    return True


async def spawn_trans(context: ContextTypes.DEFAULT_TYPE, chat_id: int, owner, exclude_ids: set[int]) -> bool:
    """Spawn de transmutación: aparte del general, solo para owner, TTL 10-20."""
    if chat_id in _active_trans or not POOL:
        return False
    char = None
    for _ in range(5):
        c = pick_character(exclude_ids=exclude_ids)
        if await resolve_image(c):
            char = c
            break
    if not char:
        return False
    ttl = random.randint(10, 20)
    _active_trans[chat_id] = {
        "char_id": char["id"], "ttl": ttl,
        "owner_id": owner.id, "owner_name": owner.first_name,
    }
    msg_id = await _spawn_photo(
        context, chat_id, char,
        f"✨ ¡Transmutación! ✨\n\nUn personaje misterioso solo para {owner.first_name}.\n"
        "Solo esa persona puede capturarla con /vinculo",
    )
    if msg_id:
        _active_trans[chat_id]["message_id"] = msg_id
    return True


async def lose_spawn(context: ContextTypes.DEFAULT_TYPE, chat_id: int, kind: str):
    if kind == "general":
        spawn = _active.pop(chat_id, None)
    else:
        spawn = _active_trans.pop(chat_id, None)
    if not spawn:
        return
    char = BY_ID.get(spawn["char_id"])
    if not char:
        return
    if kind == "general":
        chat_cfg(chat_id)["counter"] = 0
        save_data()
        await context.bot.send_message(
            chat_id,
            "💨 Se escapó... nadie la capturó a tiempo.\n\n"
            f"Era {reveal_text(char)}\n"
            "Ya no se puede capturar hasta que vuelva a aparecer.",
        )
    else:
        owner = spawn.get("owner_name", "esa persona")
        await context.bot.send_message(
            chat_id,
            f"💨 Se escapó la transmutación de {owner}...\n\n"
            f"Era {reveal_text(char)}\n"
            "Ya no se puede capturar hasta que vuelva a aparecer.",
        )


# ---------------------------------------------------------------- Captura

async def do_vinculo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    trans = _active_trans.get(chat.id)
    if trans and trans["owner_id"] == user.id:
        char = BY_ID.get(trans["char_id"])
        _active_trans.pop(chat.id, None)
        if char:
            await _give_character(update, user, char, "💞 ¡Transmutación capturada!")
        return
    if trans and trans["owner_id"] != user.id:
        if chat.id not in _active:
            await update.effective_message.reply_text(
                f"Este personaje de transmutación es solo para {trans['owner_name']}. "
                "Espera al spawn general."
            )
            return
    spawn = _active.get(chat.id)
    if not spawn:
        await update.effective_message.reply_text(
            "Ahora mismo no hay ningún personaje activo. Habla en el grupo y aparecerá uno."
        )
        return
    char = BY_ID.get(spawn["char_id"])
    if not char:
        _active.pop(chat.id, None)
        return
    _active.pop(chat.id, None)
    chat_cfg(chat.id)["counter"] = 0
    await _give_character(update, user, char, f"💞 ¡{user.first_name} la capturó con /vinculo!")


async def _give_character(update: Update, user, char: dict, header: str):
    entry = user_entry(user)
    coll = entry["collection"]
    coll[str(char["id"])] = int(coll.get(str(char["id"]), 0)) + 1
    save_data()
    distinct, total, points = user_stats(user.id)
    await update.effective_message.reply_text(
        f"{header}\n\n"
        f"Era {reveal_text(char)}\n"
        f"+{RARITY_POINTS[char['rarity']]} puntos\n"
        f"Tienes a {char['name']} x{coll[str(char['id'])]}\n"
        f"Colección: {total} en total ({distinct} distintos) · {points} puntos\n"
        "Mírala con /lazos"
    )


async def vinculo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await do_vinculo(update, context)


# ---------------------------------------------------------------- /lazos

def lazos_groups(uid: str) -> list[tuple[str, list[dict]]]:
    entry = _data.get("users", {}).get(str(uid))
    if not entry:
        return []
    coll = entry.get("collection", {})
    by_series: dict[str, list[dict]] = {}
    for cid_str, count in coll.items():
        char = BY_ID.get(int(cid_str))
        if not char:
            continue
        by_series.setdefault(char["series"], []).append({**char, "count": int(count)})
    groups = []
    for series in sorted(by_series.keys()):
        chars = sorted(by_series[series], key=lambda c: normalize(c["name"]))
        groups.append((series, chars))
    return groups


def lazos_text(uid: str, first_name: str, page: int) -> tuple[str, int, list[dict]]:
    groups = lazos_groups(uid)
    distinct, total, points = user_stats(uid)
    entry = _data.get("users", {}).get(str(uid)) or {}
    fav_id = entry.get("favorite")
    if not groups:
        return (
            f"💞 Lazos de {first_name}\n"
            f"Colección: {total} en total ({distinct} distintos) · {points} puntos\n\n"
            "Aún no tienes personajes. Captura el próximo que aparezca con /vinculo.",
            1, [],
        )
    total_pages = (len(groups) + SERIES_PER_PAGE - 1) // SERIES_PER_PAGE
    page = max(1, min(page, total_pages))
    page_groups = groups[(page - 1) * SERIES_PER_PAGE: page * SERIES_PER_PAGE]
    lines = [
        f"💞 Lazos de {first_name}",
        f"Colección: {total} en total ({distinct} distintos) · {points} puntos",
        f"Página {page}/{total_pages}",
        "",
    ]
    chars_on_page: list[dict] = []
    for series, chars in page_groups:
        lines.append(f"{series} {SERIES_TOTAL.get(series, len(chars))}/{len(chars)}")
        for c in chars:
            mark = "❤️" if fav_id and int(fav_id) == c["id"] else ""
            lines.append(f"{c['id']}. {c['name']} [{c['count']}] {mark}".rstrip())
            chars_on_page.append(c)
        lines.append("")
    return "\n".join(lines).rstrip(), total_pages, chars_on_page


def lazos_keyboard(uid: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    # Diseño propio: Inicio / Anterior / Siguiente / Fin, luego Inline y Cerrar.
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("« Anterior", callback_data=f"lz:p:{uid}:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Siguiente »", callback_data=f"lz:p:{uid}:{page + 1}"))
    buttons = []
    if nav:
        buttons.append(nav)
    buttons.append([
        InlineKeyboardButton("⏮️ Inicio", callback_data=f"lz:f:{uid}"),
        InlineKeyboardButton("Fin ⏭️", callback_data=f"lz:l:{uid}"),
    ])
    buttons.append([
        InlineKeyboardButton("Inline 🌐", switch_inline_query_current_chat=f"lazos {uid}"),
        InlineKeyboardButton("✖️ Cerrar", callback_data=f"lz:c:{uid}"),
    ])
    return InlineKeyboardMarkup(buttons)


async def lazos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    entry = _data.get("users", {}).get(str(user.id)) or {}
    fav_id = entry.get("favorite")
    if fav_id and int(fav_id) in BY_ID:
        fav = BY_ID[int(fav_id)]
        if int(entry.get("collection", {}).get(str(fav_id), 0)) > 0:
            url = await resolve_image(fav)
            if url:
                try:
                    await update.effective_message.reply_photo(
                        photo=url,
                        caption=f"💖 Favorita de {user.first_name}: {fav['name']} — {fav['series']} {stars(fav['rarity'])}",
                    )
                except Exception:
                    pass
    text, total_pages, _ = lazos_text(str(user.id), user.first_name, 1)
    await update.effective_message.reply_text(
        text, reply_markup=lazos_keyboard(user.id, 1, total_pages)
    )


# ---------------------------------------------------------------- Inline (galería)

async def on_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    user = query.from_user
    parts = (query.query or "").strip().split()
    if len(parts) < 2 or parts[0] != "lazos":
        await query.answer([], switch_pm_text="Usa /lazos en el grupo y pulsa Inline 🌐",
                           switch_pm_parameter="start")
        return
    try:
        owner_id = int(parts[1])
    except ValueError:
        await query.answer([])
        return
    if user.id != owner_id:
        await query.answer([
            InlineQueryResultArticle(
                id="nope", title="Esta colección no es tuya",
                input_message_content=InputTextMessageContent("Esta colección no es tuya."),
            )
        ], cache_time=1)
        return
    groups = lazos_groups(str(owner_id))
    chars: list[dict] = []
    for _, cs in groups:
        chars.extend(cs)
    results = []
    for c in chars[:50]:
        url = _image_cache.get(c["id"])
        if not url:
            if len(results) >= 10:
                continue
            url = await resolve_image(c)
        if not url:
            continue
        results.append(InlineQueryResultPhoto(
            id=f"char-{c['id']}",
            photo_url=url, thumb_url=url,
            title=c["name"],
            description=f"{c['series']} • {stars(c['rarity'])} • x{c['count']}",
            caption=f"{c['name']} — {c['series']} {stars(c['rarity'])} x{c['count']}",
        ))
    await query.answer(results, cache_time=10)


# ---------------------------------------------------------------- /list y /podio

def list_text(page: int) -> tuple[str, int]:
    series = sorted(SERIES_TOTAL.keys())
    total_pages = (len(series) + LIST_PER_PAGE - 1) // LIST_PER_PAGE
    page = max(1, min(page, total_pages))
    chunk = series[(page - 1) * LIST_PER_PAGE: page * LIST_PER_PAGE]
    lines = [
        "📚 Series del bot",
        f"Total: {len(POOL)} personajes · {len(series)} series",
        f"Página {page}/{total_pages}",
        "",
    ]
    for s in chunk:
        lines.append(f"{s} — {SERIES_TOTAL[s]}")
    return "\n".join(lines), total_pages


def list_keyboard(uid: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("« Anterior", callback_data=f"ls:p:{uid}:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Siguiente »", callback_data=f"ls:p:{uid}:{page + 1}"))
    buttons = []
    if nav:
        buttons.append(nav)
    buttons.append([
        InlineKeyboardButton("⏮️ Inicio", callback_data=f"ls:f:{uid}"),
        InlineKeyboardButton("Fin ⏭️", callback_data=f"ls:l:{uid}"),
        InlineKeyboardButton("✖️ Cerrar", callback_data=f"ls:c:{uid}"),
    ])
    return InlineKeyboardMarkup(buttons)


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, total_pages = list_text(1)
    await update.effective_message.reply_text(
        text, reply_markup=list_keyboard(update.effective_user.id, 1, total_pages)
    )


async def podio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = _data.get("users", {})
    ranking = []
    for uid, entry in users.items():
        distinct, total, points = user_stats(uid)
        if distinct:
            ranking.append((distinct, points, entry.get("username", "?")))
    if not ranking:
        await update.effective_message.reply_text("🏆 Aún no hay capturas. ¡Sé la primera persona en capturar!")
        return
    ranking.sort(reverse=True)
    lines = ["🏆 Podio de Lazos\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (distinct, points, name) in enumerate(ranking[:10], 1):
        medal = medals[i - 1] if i <= 3 else f"{i}."
        lines.append(f"{medal} {name} — {distinct} distintos · {points} puntos")
    await update.effective_message.reply_text("\n".join(lines))


# ---------------------------------------------------------------- /atesorar

async def atesorar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args or []
    entry = user_entry(user)
    if not args:
        fav_id = entry.get("favorite")
        if not fav_id or int(fav_id) not in BY_ID:
            await update.effective_message.reply_text(
                "No tienes favorita marcada. Usa /atesorar <id>  — el ID lo ves en /lazos."
            )
            return
        fav = BY_ID[int(fav_id)]
        await update.effective_message.reply_text(
            f"💖 Tu favorita es {fav['name']} de {fav['series']} {stars(fav['rarity'])}"
        )
        return
    try:
        char_id = int(args[0])
    except ValueError:
        await update.effective_message.reply_text("El ID debe ser un número. Míralo en /lazos.")
        return
    if char_id == 0:
        entry["favorite"] = None
        save_data()
        await update.effective_message.reply_text("Ya no tienes favorita marcada.")
        return
    char = BY_ID.get(char_id)
    if not char:
        await update.effective_message.reply_text("No existe ningún personaje con ese ID.")
        return
    if int(entry["collection"].get(str(char_id), 0)) <= 0:
        await update.effective_message.reply_text(f"No tienes a {char['name']} en tu colección.")
        return
    entry["favorite"] = char_id
    save_data()
    await update.effective_message.reply_text(
        f"💖 Tu favorita ahora es {char['name']} de {char['series']} {stars(char['rarity'])}.\n"
        "Saldrá con su foto arriba en /lazos."
    )


# ---------------------------------------------------------------- /tributo y /liberar

async def tributo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args or []
    if not args:
        await update.effective_message.reply_text(
            "Uso: responde al mensaje de la persona y escribe /tributo <id>\nEjemplo: /tributo 2"
        )
        return
    try:
        char_id = int(args[0])
    except ValueError:
        await update.effective_message.reply_text("El ID debe ser un número. Míralo en /lazos.")
        return
    char = BY_ID.get(char_id)
    if not char:
        await update.effective_message.reply_text("No existe ningún personaje con ese ID.")
        return
    recipient = None
    if update.effective_message.reply_to_message:
        recipient = update.effective_message.reply_to_message.from_user
    elif len(args) >= 2:
        try:
            rid = int(args[1])
            recipient = type("U", (), {"id": rid, "first_name": "esa persona", "username": None, "is_bot": False})()
        except ValueError:
            await update.effective_message.reply_text(
                "No puedo encontrar a esa persona por @usuario. "
                "Responde a uno de sus mensajes y escribe /tributo <id>."
            )
            return
    if not recipient:
        await update.effective_message.reply_text(
            f"¿A quién se la donas? Responde al mensaje de esa persona y escribe /tributo {char_id}"
        )
        return
    if recipient.id == user.id:
        await update.effective_message.reply_text("No puedes donarte un personaje a ti misma/o.")
        return
    if getattr(recipient, "is_bot", False):
        await update.effective_message.reply_text("No puedes donar un personaje a un bot.")
        return
    entry = user_entry(user)
    if int(entry["collection"].get(str(char_id), 0)) <= 0:
        await update.effective_message.reply_text(f"No tienes a {char['name']} en tu colección.")
        return
    entry["collection"][str(char_id)] = int(entry["collection"][str(char_id)]) - 1
    if entry["collection"][str(char_id)] <= 0:
        del entry["collection"][str(char_id)]
        if entry.get("favorite") == char_id:
            entry["favorite"] = None
    dest = user_entry(recipient)
    dest["collection"][str(char_id)] = int(dest["collection"].get(str(char_id), 0)) + 1
    save_data()
    await update.effective_message.reply_text(
        f"🎁 {user.first_name} le donó a {recipient.first_name} a "
        f"{char['name']} de {char['series']} {stars(char['rarity'])}"
    )


async def liberar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args or []
    if not args:
        await update.effective_message.reply_text("Uso: /liberar <id>  — el ID lo ves en /lazos.")
        return
    try:
        char_id = int(args[0])
    except ValueError:
        await update.effective_message.reply_text("El ID debe ser un número. Míralo en /lazos.")
        return
    char = BY_ID.get(char_id)
    if not char:
        await update.effective_message.reply_text("No existe ningún personaje con ese ID.")
        return
    entry = _data.get("users", {}).get(str(user.id))
    if not entry or int(entry.get("collection", {}).get(str(char_id), 0)) <= 0:
        await update.effective_message.reply_text(f"No tienes a {char['name']} en tu colección.")
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Sí, liberarla", callback_data=f"lb:y:{user.id}:{char_id}"),
        InlineKeyboardButton("No, cancelar", callback_data=f"lb:n:{user.id}:{char_id}"),
    ]])
    await update.effective_message.reply_text(
        f"¿Seguro que quieres liberar a {char['name']} de {char['series']}?\nPerderás una copia para siempre.",
        reply_markup=keyboard,
    )


# ---------------------------------------------------------------- /pactar (trueque)

async def pactar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flujo:
    1) A responde a un mensaje de B con /pactar <id_de_A>
    2) El bot publica el trueque y le pide a B que responda a ESE mensaje con /pactar <id_de_B>
    3) El bot muestra confirmación con botones Aceptar/Cancelar, solo A y B pueden pulsar.
    4) Cuando los dos aceptan, se intercambian. Caduca en 5 minutos.
    """
    user = update.effective_user
    chat = update.effective_chat
    args = context.args or []
    msg = update.effective_message

    if msg.reply_to_message and msg.reply_to_message.message_id in _trades_by_msg:
        trade_id = _trades_by_msg[msg.reply_to_message.message_id]
        trade = _trades.get(trade_id)
        if not trade:
            await msg.reply_text("Ese trueque ya no está activo.")
            return
        if user.id != trade["b_id"]:
            await msg.reply_text("Solo la persona a la que le propusieron el trueque puede responder aquí.")
            return
        if trade["stage"] != "waiting_b":
            await msg.reply_text("Este trueque ya está en confirmación, usa los botones.")
            return
        if not args:
            await msg.reply_text("Escribe /pactar <id> con el ID que quieres ofrecer.")
            return
        try:
            b_char_id = int(args[0])
        except ValueError:
            await msg.reply_text("El ID debe ser un número. Míralo en /lazos.")
            return
        b_char = BY_ID.get(b_char_id)
        if not b_char:
            await msg.reply_text("No existe ningún personaje con ese ID.")
            return
        b_entry = _data.get("users", {}).get(str(user.id))
        if not b_entry or int(b_entry.get("collection", {}).get(str(b_char_id), 0)) <= 0:
            await msg.reply_text(f"No tienes a {b_char['name']} en tu colección.")
            return
        trade["b_char_id"] = b_char_id
        trade["stage"] = "confirm"
        trade["a_accept"] = False
        trade["b_accept"] = False
        a_char = BY_ID[trade["a_char_id"]]
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Aceptar", callback_data=f"pc:a:{trade_id}"),
            InlineKeyboardButton("❌ Cancelar", callback_data=f"pc:x:{trade_id}"),
        ]])
        try:
            await context.bot.edit_message_text(
                chat_id=chat.id, message_id=trade["message_id"],
                text=(
                    "🤝 Trueque\n\n"
                    f"{trade['a_name']} ofrece: {a_char['name']} de {a_char['series']} {stars(a_char['rarity'])}\n"
                    f"{trade['b_name']} ofrece: {b_char['name']} de {b_char['series']} {stars(b_char['rarity'])}\n\n"
                    "Los dos tienen que dar a ✅ Aceptar. Solo ellos pueden pulsar."
                ),
                reply_markup=keyboard,
            )
        except Exception:
            pass
        return

    if not args:
        await msg.reply_text(
            "Uso: responde al mensaje de la otra persona y escribe /pactar <id>\nEjemplo: /pactar 178"
        )
        return
    if not msg.reply_to_message:
        await msg.reply_text(
            "Responde al mensaje de la persona con la que quieres intercambiar y escribe /pactar <id>."
        )
        return
    try:
        a_char_id = int(args[0])
    except ValueError:
        await msg.reply_text("El ID debe ser un número. Míralo en /lazos.")
        return
    a_char = BY_ID.get(a_char_id)
    if not a_char:
        await msg.reply_text("No existe ningún personaje con ese ID.")
        return
    recipient = msg.reply_to_message.from_user
    if recipient.id == user.id:
        await msg.reply_text("No puedes hacer un trueque contigo misma/o.")
        return
    if recipient.is_bot:
        await msg.reply_text("No puedes hacer un trueque con un bot.")
        return
    entry = _data.get("users", {}).get(str(user.id))
    if not entry or int(entry.get("collection", {}).get(str(a_char_id), 0)) <= 0:
        await msg.reply_text(f"No tienes a {a_char['name']} en tu colección.")
        return
    for t in _trades.values():
        if t["chat_id"] == chat.id and {t["a_id"], t["b_id"]} == {user.id, recipient.id}:
            await msg.reply_text("Ya hay un trueque activo entre ustedes. Termínalo o cancélalo primero.")
            return
    _trade_counter[0] += 1
    trade_id = _trade_counter[0]
    sent = await msg.reply_text(
        f"🤝 Trueque propuesto\n\n"
        f"{user.first_name} ofrece: {a_char['name']} de {a_char['series']} {stars(a_char['rarity'])}\n\n"
        f"{recipient.first_name}, responde a ESTE mensaje con /pactar <id> para ofrecer la tuya.\n"
        "Solo ustedes dos pueden interactuar con este trueque. Caduca en 5 minutos."
    )
    _trades[trade_id] = {
        "chat_id": chat.id, "message_id": sent.message_id,
        "a_id": user.id, "a_name": user.first_name, "a_char_id": a_char_id,
        "b_id": recipient.id, "b_name": recipient.first_name, "b_char_id": None,
        "stage": "waiting_b", "a_accept": False, "b_accept": False,
        "created_at": time.time(),
    }
    _trades_by_msg[sent.message_id] = trade_id


async def check_trades(context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    expired = [tid for tid, t in _trades.items() if now - t["created_at"] > TRADE_TIMEOUT]
    for tid in expired:
        trade = _trades.pop(tid, None)
        if not trade:
            continue
        _trades_by_msg.pop(trade["message_id"], None)
        try:
            await context.bot.edit_message_text(
                chat_id=trade["chat_id"], message_id=trade["message_id"],
                text="🤝 Trueque caducado (pasaron 5 minutos sin completarse).",
            )
        except Exception:
            pass


# ---------------------------------------------------------------- /transmutar

async def transmutar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    args = context.args or []
    if len(args) != 3:
        await update.effective_message.reply_text(
            "Uso: /transmutar <id> <id> <id>\n"
            "Das 3 vínculos tuyos (repetidos o no) y sale un personaje al azar solo para ti.\n"
            "Ejemplo: /transmutar 178 45 12"
        )
        return
    try:
        ids = [int(a) for a in args]
    except ValueError:
        await update.effective_message.reply_text("Los tres deben ser números (IDs). Míralos en /lazos.")
        return
    for cid in ids:
        if cid not in BY_ID:
            await update.effective_message.reply_text(f"No existe ningún personaje con el ID {cid}.")
            return
    if chat.id in _active_trans:
        await update.effective_message.reply_text(
            "Ya hay una transmutación activa en este grupo. Espera a que termine."
        )
        return
    entry = user_entry(user)
    coll = entry["collection"]
    need = Counter(ids)
    for cid, n in need.items():
        if int(coll.get(str(cid), 0)) < n:
            await update.effective_message.reply_text(
                f"No tienes suficientes copias de {BY_ID[cid]['name']} (tienes {coll.get(str(cid), 0)}, necesitas {n})."
            )
            return
    given_names = []
    for cid, n in need.items():
        given_names.append(BY_ID[cid]["name"])
        coll[str(cid)] = int(coll[str(cid)]) - n
        if coll[str(cid)] <= 0:
            del coll[str(cid)]
            if entry.get("favorite") == cid:
                entry["favorite"] = None
    save_data()
    ok = await spawn_trans(context, chat.id, user, exclude_ids=set(ids))
    if not ok:
        for cid, n in need.items():
            coll[str(cid)] = int(coll.get(str(cid), 0)) + n
        save_data()
        await update.effective_message.reply_text(
            "No pude hacer la transmutación ahora, te devolví tus 3 personajes. Inténtalo de nuevo."
        )
        return
    await update.effective_message.reply_text(
        f"🔮 {user.first_name} transmutó {', '.join(given_names)} y apareció un personaje solo para esa persona.\n"
        "Dura entre 10 y 20 mensajes. ¡Captúrala con /vinculo antes de que se escape!"
    )


# ---------------------------------------------------------------- Admins / owner

async def _member_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status
    except Exception:
        return ""


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return (await _member_status(update, context)) in ("administrator", "creator")


async def is_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return (await _member_status(update, context)) == "creator"


async def timepawn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.effective_message.reply_text(
            "Solo los administradores del grupo pueden cambiar cada cuántos mensajes aparece un personaje."
        )
        return
    args = context.args or []
    if not args:
        cfg = chat_cfg(update.effective_chat.id)
        await update.effective_message.reply_text(
            f"Ahora aparece un personaje cada {cfg['spawn_every']} mensajes.\n"
            "Para cambiarlo: /timepawn <número>  (entre 10 y 500)"
        )
        return
    try:
        n = int(args[0])
    except ValueError:
        await update.effective_message.reply_text("Escribe un número, por ejemplo: /timepawn 50")
        return
    if n < 10 or n > 500:
        await update.effective_message.reply_text("El número debe estar entre 10 y 500 mensajes.")
        return
    cfg = chat_cfg(update.effective_chat.id)
    cfg["spawn_every"] = n
    cfg["counter"] = 0
    save_data()
    await update.effective_message.reply_text(
        f"✅ Listo. A partir de ahora aparecerá un personaje cada {n} mensajes."
    )


async def invocar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text("Esto es para grupos.")
        return
    args = context.args or []
    if args:
        if not await is_owner(update, context):
            await update.effective_message.reply_text(
                "Solo el propietario del grupo puede invocar un personaje por ID. "
                "Los administradores solo pueden invocar al azar con /invocar."
            )
            return
        try:
            char_id = int(args[0])
        except ValueError:
            await update.effective_message.reply_text("El ID debe ser un número.")
            return
        char = BY_ID.get(char_id)
        if not char:
            await update.effective_message.reply_text("No existe ningún personaje con ese ID.")
            return
        if chat.id in _active:
            await update.effective_message.reply_text("Ya hay un personaje activo esperando a ser capturado 👀")
            return
        await spawn_character(context, chat.id, char=char)
        return
    if not await is_admin(update, context):
        await update.effective_message.reply_text("Solo los administradores pueden forzar un spawn con /invocar.")
        return
    if chat.id in _active:
        await update.effective_message.reply_text("Ya hay un personaje activo esperando a ser capturado 👀")
        return
    await spawn_character(context, chat.id)


# ---------------------------------------------------------------- Callbacks

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    parts = (query.data or "").split(":")
    if not parts:
        await query.answer()
        return

    if parts[0] == "lz":
        if len(parts) < 3:
            await query.answer()
            return
        owner_id = int(parts[2])
        if user.id != owner_id:
            await query.answer("Esta colección no es tuya.", show_alert=True)
            return
        if parts[1] == "c":
            try:
                await query.delete_message()
            except Exception:
                await query.edit_message_text("Listado cerrado.")
            await query.answer()
            return
        if parts[1] == "f":
            page = 1
        elif parts[1] == "l":
            _, total_pages, _ = lazos_text(str(owner_id), user.first_name, 9999)
            page = total_pages
        else:
            page = int(parts[3])
        text, total_pages, _ = lazos_text(str(owner_id), user.first_name, page)
        try:
            await query.edit_message_text(text, reply_markup=lazos_keyboard(owner_id, page, total_pages))
        except Exception:
            pass
        await query.answer()
        return

    if parts[0] == "ls":
        owner_id = int(parts[2])
        if user.id != owner_id:
            await query.answer("Este listado no es tuyo.", show_alert=True)
            return
        if parts[1] == "c":
            try:
                await query.delete_message()
            except Exception:
                await query.edit_message_text("Listado cerrado.")
            await query.answer()
            return
        if parts[1] == "f":
            page = 1
        elif parts[1] == "l":
            _, total_pages = list_text(9999)
            page = total_pages
        else:
            page = int(parts[3])
        text, total_pages = list_text(page)
        try:
            await query.edit_message_text(text, reply_markup=list_keyboard(owner_id, page, total_pages))
        except Exception:
            pass
        await query.answer()
        return

    if parts[0] == "lb":
        owner_id = int(parts[2])
        char_id = int(parts[3])
        if user.id != owner_id:
            await query.answer("Esto no es tuyo.", show_alert=True)
            return
        char = BY_ID.get(char_id)
        if parts[1] == "n":
            await query.edit_message_text("Cancelado, no se liberó nada.")
            await query.answer()
            return
        entry = _data.get("users", {}).get(str(owner_id))
        if not entry or int(entry.get("collection", {}).get(str(char_id), 0)) <= 0:
            await query.edit_message_text("Ya no tienes ese personaje.")
            await query.answer()
            return
        coll = entry["collection"]
        coll[str(char_id)] = int(coll[str(char_id)]) - 1
        if coll[str(char_id)] <= 0:
            del coll[str(char_id)]
            if entry.get("favorite") == char_id:
                entry["favorite"] = None
        save_data()
        name = char["name"] if char else f"#{char_id}"
        await query.edit_message_text(f"🕊️ Liberaste a {name}. Ya no está en tu colección.")
        await query.answer()
        return

    if parts[0] == "pc":
        trade_id = int(parts[2])
        trade = _trades.get(trade_id)
        if not trade:
            await query.answer("Ese trueque ya no está activo.", show_alert=True)
            return
        if user.id not in (trade["a_id"], trade["b_id"]):
            await query.answer("Este trueque no es tuyo.", show_alert=True)
            return
        if parts[1] == "x":
            _trades.pop(trade_id, None)
            _trades_by_msg.pop(trade["message_id"], None)
            await query.edit_message_text("🤝 Trueque cancelado.")
            await query.answer()
            return
        if user.id == trade["a_id"]:
            trade["a_accept"] = True
        else:
            trade["b_accept"] = True
        if not (trade["a_accept"] and trade["b_accept"]):
            a_char = BY_ID[trade["a_char_id"]]
            b_char = BY_ID[trade["b_char_id"]]
            who = "✅ A aceptó" if trade["a_accept"] else "⏳ Falta A"
            who2 = "✅ B aceptó" if trade["b_accept"] else "⏳ Falta B"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Aceptar", callback_data=f"pc:a:{trade_id}"),
                InlineKeyboardButton("❌ Cancelar", callback_data=f"pc:x:{trade_id}"),
            ]])
            try:
                await query.edit_message_text(
                    text=(
                        "🤝 Trueque\n\n"
                        f"{trade['a_name']} ofrece: {a_char['name']} de {a_char['series']} {stars(a_char['rarity'])}\n"
                        f"{trade['b_name']} ofrece: {b_char['name']} de {b_char['series']} {stars(b_char['rarity'])}\n\n"
                        f"{trade['a_name']}: {who}\n{trade['b_name']}: {who2}"
                    ),
                    reply_markup=keyboard,
                )
            except Exception:
                pass
            await query.answer("Aceptado. Falta la otra persona.")
            return
        a_entry = _data.get("users", {}).get(str(trade["a_id"]))
        b_entry = _data.get("users", {}).get(str(trade["b_id"]))
        a_ok = a_entry and int(a_entry.get("collection", {}).get(str(trade["a_char_id"]), 0)) > 0
        b_ok = b_entry and int(b_entry.get("collection", {}).get(str(trade["b_char_id"]), 0)) > 0
        if not (a_ok and b_ok):
            _trades.pop(trade_id, None)
            _trades_by_msg.pop(trade["message_id"], None)
            await query.edit_message_text("🤝 Trueque cancelado: alguien ya no tenía su personaje.")
            await query.answer()
            return
        for src, dst, cid in [
            (a_entry, b_entry, trade["a_char_id"]),
            (b_entry, a_entry, trade["b_char_id"]),
        ]:
            src["collection"][str(cid)] = int(src["collection"][str(cid)]) - 1
            if src["collection"][str(cid)] <= 0:
                del src["collection"][str(cid)]
                if src.get("favorite") == cid:
                    src["favorite"] = None
            dst["collection"][str(cid)] = int(dst["collection"].get(str(cid), 0)) + 1
        save_data()
        a_char = BY_ID[trade["a_char_id"]]
        b_char = BY_ID[trade["b_char_id"]]
        _trades.pop(trade_id, None)
        _trades_by_msg.pop(trade["message_id"], None)
        await query.edit_message_text(
            f"✅ ¡Trueque completado!\n\n"
            f"{trade['a_name']} recibió a {b_char['name']} de {b_char['series']}\n"
            f"{trade['b_name']} recibió a {a_char['name']} de {a_char['series']}"
        )
        await query.answer()
        return

    await query.answer()


# ---------------------------------------------------------------- Inicio / mensajes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg_every = DEFAULT_SPAWN_EVERY
    if update.effective_chat.type in ("group", "supergroup"):
        cfg_every = chat_cfg(update.effective_chat.id)["spawn_every"]
    await update.effective_message.reply_text(
        "💞 ¡Hola! Soy el bot gacha de Lazos.\n\n"
        f"Cada {cfg_every} mensajes del grupo aparece una chica misteriosa de anime o videojuego, "
        "solo con su imagen, sin nombre, sin serie y sin pistas.\n"
        "Dura solo entre 5 y 10 mensajes: captúrala rápido con /vinculo.\n"
        "Si se escapa, te diré quién era y de dónde venía.\n\n"
        "Para todos:\n"
        "/vinculo - capturar al personaje activo\n"
        "/lazos - tu colección (páginas, Inline, favorita arriba)\n"
        "/tributo <id> - donar (responde a esa persona)\n"
        "/liberar <id> - eliminar un personaje tuyo\n"
        "/pactar <id> - intercambiar (responde a esa persona)\n"
        "/transmutar <id> <id> <id> - das 3 y sale una solo para ti\n"
        "/atesorar <id> - marcar tu única favorita\n"
        "/podio - ranking del grupo\n"
        "/list - series y personajes que tiene el bot\n\n"
        "Solo admins:\n"
        "/invocar - spawnear al azar\n"
        "/timepawn <n> - cada cuántos mensajes aparece\n\n"
        "Solo el propietario del grupo:\n"
        "/invocar <id> - spawnear ese personaje concreto"
    )


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cuenta mensajes del grupo.
    - Sin spawn general activo: cuenta hacia el próximo (cada N).
    - Con spawn general activo: cada mensaje le quita 1 de vida (5-10).
    - La transmutación es aparte: cada mensaje también le quita 1 (10-20),
      y no resetea ni bloquea el contador general.
    """
    msg = update.effective_message
    if not msg or not msg.text or update.effective_user.is_bot:
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return
    if normalize(msg.text).startswith("vinculo"):
        await do_vinculo(update, context)
        return

    cfg = chat_cfg(chat.id)
    if chat.id in _active:
        _active[chat.id]["ttl"] -= 1
        if _active[chat.id]["ttl"] <= 0:
            await lose_spawn(context, chat.id, "general")
    else:
        cfg["counter"] = int(cfg.get("counter", 0)) + 1
        if cfg["counter"] >= int(cfg.get("spawn_every", DEFAULT_SPAWN_EVERY)):
            await spawn_character(context, chat.id)

    if chat.id in _active_trans:
        _active_trans[chat.id]["ttl"] -= 1
        if _active_trans[chat.id]["ttl"] <= 0:
            await lose_spawn(context, chat.id, "trans")


async def vinculo_acentuado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captura si escriben /vínculo con acento. Telegram no permite registrar
    un comando con acento (CommandHandler lo rechaza y el bot se cae al arrancar),
    así que se atiende como texto con este handler aparte."""
    await do_vinculo(update, context)


def main():
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_TOKEN. Copia .env.example a .env y pon el token de BotFather.")
    if not POOL:
        raise SystemExit("characters.json está vacío o no se pudo leer.")
    app = ApplicationBuilder().token(TOKEN).build()

    for cmd, fn in [
        ("start", start), ("ayuda", ayuda), ("help", ayuda),
        ("vinculo", vinculo),
        ("lazos", lazos), ("Lazos", lazos),
        ("tributo", tributo), ("Tributo", tributo),
        ("liberar", liberar), ("Liberar", liberar),
        ("pactar", pactar), ("Pactar", pactar),
        ("transmutar", transmutar), ("Transmutar", transmutar),
        ("atesorar", atesorar), ("Atesorar", atesorar),
        ("podio", podio), ("Podio", podio), ("top", podio),
        ("list", list_cmd), ("List", list_cmd),
        ("timepawn", timepawn), ("Timepawn", timepawn),
        ("spawn_cada", timepawn), ("config_spawn", timepawn),
        ("invocar", invocar), ("Invocar", invocar),
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    # /vínculo con acento: no se puede registrar como comando, se atiende por regex.
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^/v[íi]nculo\b"), vinculo_acentuado))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(InlineQueryHandler(on_inline))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    if app.job_queue:
        app.job_queue.run_repeating(check_trades, interval=30, first=30)

    logger.info("Bot Lazos v3 iniciado. Pool: %s personajes, %s series. Spawn cada %s mensajes.",
                len(POOL), len(SERIES_TOTAL), DEFAULT_SPAWN_EVERY)
    app.run_polling()


if __name__ == "__main__":
    main()
