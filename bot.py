"""
Bot Gacha de Anime para Telegram
================================
- Cada N mensajes en un grupo (por defecto 20) aparece un personaje misterioso.
- Solo muestra la imagen / fanart, NUNCA el nombre ni el anime en el mensaje de spawn.
- Los usuarios adivinan escribiendo el nombre en el chat o con /adivina <nombre>.
- Quien acierta primero se queda el personaje en su colección y gana puntos por rareza.
- /pista, /coleccion, /top, /invocar

Imágenes: API gratuita de Jikan (MyAnimeList), sin clave.
  GET https://api.jikan.moe/v4/top/characters?page=X&limit=25
  -> data[].name, data[].images.jpg.image_url, data[].favorites
  -> data[].anime[0].anime.title  (solo se revela DESPUÉS de acertar)
  Opcional: GET /v4/characters/{id}/pictures para variar la imagen.

Instalación:
  pip install -r requirements.txt
  cp .env.example .env   # pon tu token de BotFather
  python bot.py
"""

import asyncio
import difflib
import json
import logging
import os
import random
import re
import time
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("gacha-bot")

# ---------------------------------------------------------------- Config
TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
SPAWN_EVERY = int(os.getenv("SPAWN_EVERY", "20"))        # mensajes para que aparezca uno
SPAWN_TIMEOUT = int(os.getenv("SPAWN_TIMEOUT", "180"))   # segundos para adivinar (3 min)
DATA_FILE = Path(__file__).parent / "data.json"
JIKAN = "https://api.jikan.moe/v4"

if not TOKEN:
    logger.warning("Falta TELEGRAM_TOKEN. Crea un .env a partir de .env.example")

# ---------------------------------------------------------------- Datos
# Colecciones guardadas en data.json:
# { "123456": {"username": "edgar", "points": 120, "characters": [{name, anime, rarity, image_url, caught_at}] } }
_data: dict = {}
if DATA_FILE.exists():
    try:
        _data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("No se pudo leer data.json: %s", e)


def save_data():
    try:
        DATA_FILE.write_text(json.dumps(_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("No se pudo guardar data.json: %s", e)


# Estado por chat (en memoria, se reinicia al apagar el bot)
_counters: dict[int, int] = {}   # chat_id -> mensajes desde el último spawn
_active: dict[int, dict] = {}    # chat_id -> {character, spawned_at, message_id}
_last_guess: dict[tuple[int, int], float] = {}  # (chat_id, user_id) -> timestamp

# Personajes de respaldo si Jikan falla en el top: se buscan por nombre en Jikan.
FALLBACK_NAMES = [
    "Monkey D. Luffy", "Naruto Uzumaki", "Goku", "Levi Ackerman",
    "Eren Yeager", "Light Yagami", "Lelouch Lamperouge", "Edward Elric",
    "Saitama", "Tanjiro Kamado", "Nezuko Kamado", "Gojo Satoru",
    "Itachi Uchiha", "Kakashi Hatake", "Sasuke Uchiha", "Sakura Haruno",
    "Ichigo Kurosaki", "Rukia Kuchiki", "Natsu Dragneel", "Erza Scarlet",
    "Midoriya Izuku", "Bakugo Katsuki", "Todoroki Shoto", "All Might",
    "Spike Spiegel", "Edward Wong", "Vash the Stampede", "Alucard",
    "Kirito", "Asuna Yuuki", "Rem", "Emilia",
    "Saber", "Rin Tohsaka", "Gintoki Sakata", "Kagura",
    "Shinji Ikari", "Rei Ayanami", "Asuka Langley", "Vegeta",
]

# ---------------------------------------------------------------- Utilidades

def normalize(text: str) -> str:
    """Quita acentos, pasa a minúsculas y deja solo letras/números/espacios."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def rarity_for(favorites: int) -> tuple[str, int]:
    """Rareza y puntos según cuántos favoritos tiene en MyAnimeList."""
    if favorites >= 40000:
        return "⭐⭐⭐⭐⭐ LEGENDARIO", 100
    if favorites >= 15000:
        return "⭐⭐⭐⭐ ÉPICO", 50
    if favorites >= 5000:
        return "⭐⭐⭐ RARO", 25
    return "⭐ COMÚN", 10


def is_correct_guess(guess: str, full_name: str) -> bool:
    """Acepta nombre completo, solo el nombre o solo el apellido. Ej: 'Luffy', 'Monkey D. Luffy'."""
    g = normalize(guess)
    name = normalize(full_name)
    if not g or len(g) < 3 or not name:
        return False
    if g == name:
        return True
    parts = name.split()
    # Nombre o apellido solos
    if g == parts[0] or g == parts[-1]:
        return True
    # Sin espacios, por si escriben "MonkeyDLuffy"
    if g.replace(" ", "") == name.replace(" ", ""):
        return True
    return False


def _parse_character(item: dict) -> dict | None:
    """Acepta tanto el formato de /top/characters como el de /characters?q=."""
    char = item.get("character") or item  # /anime/{id}/characters anida en "character"
    name = char.get("name")
    images = char.get("images") or {}
    jpg = images.get("jpg") or {}
    image_url = jpg.get("image_url") or jpg.get("large_image_url")
    if not name or not image_url:
        return None

    anime_title = "Anime desconocido"
    anime_list = item.get("anime") or char.get("anime") or []
    if anime_list:
        first = anime_list[0]
        # Puede ser {"anime": {"title": ...}} o {"title": ...}
        anime_obj = first.get("anime") or first
        anime_title = anime_obj.get("title") or anime_title

    favorites = int(char.get("favorites") or item.get("favorites") or 0)
    rarity, points = rarity_for(favorites)
    return {
        "name": name,
        "anime": anime_title,
        "image_url": image_url,
        "favorites": favorites,
        "rarity": rarity,
        "points": points,
        "mal_id": char.get("mal_id"),
    }


def _fetch_json(url: str) -> dict:
    resp = requests.get(url, timeout=12, headers={"User-Agent": "telegram-gacha-bot/1.0"})
    resp.raise_for_status()
    return resp.json()


async def get_random_character() -> dict | None:
    """Elige un personaje al azar de Jikan. Devuelve dict o None si falla todo."""
    def _work() -> dict | None:
        # 1) Top de personajes, página al azar (25 por página)
        try:
            page = random.randint(1, 10)
            data = _fetch_json(f"{JIKAN}/top/characters?page={page}&limit=25")
            items = data.get("data") or []
            random.shuffle(items)
            for item in items:
                char = _parse_character(item)
                if char:
                    # 2) Intentar una imagen variada (a veces fanart) del personaje
                    try:
                        if char.get("mal_id"):
                            pics = _fetch_json(f"{JIKAN}/characters/{char['mal_id']}/pictures")
                            pic_list = pics.get("data") or []
                            if pic_list:
                                pic = random.choice(pic_list)
                                url = (pic.get("jpg") or {}).get("image_url")
                                if url:
                                    char["image_url"] = url
                    except Exception:
                        pass  # si falla, nos quedamos con la imagen principal
                    return char
        except Exception as e:
            logger.warning("Jikan top falló: %s", e)

        # 3) Respaldo: buscar un nombre conocido
        try:
            name = random.choice(FALLBACK_NAMES)
            data = _fetch_json(
                f"{JIKAN}/characters?q={requests.utils.quote(name)}&limit=1"
            )
            items = data.get("data") or []
            if items:
                return _parse_character(items[0])
        except Exception as e:
            logger.warning("Jikan búsqueda de respaldo falló: %s", e)
        return None

    return await asyncio.to_thread(_work)


# ---------------------------------------------------------------- Spawn

async def spawn_character(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """Lanza un personaje misterioso. Devuelve False si ya hay uno activo o falla la API."""
    if chat_id in _active:
        return False

    char = await get_random_character()
    if not char:
        await context.bot.send_message(
            chat_id, "😿 No pude cargar un personaje ahora. Intenta con /invocar en un momento."
        )
        return False

    _active[chat_id] = {"character": char, "spawned_at": time.time()}
    _counters[chat_id] = 0

    # IMPORTANTE: el caption NO incluye nombre ni anime, solo la imagen + rareza.
    caption = (
        "✨ ¡Ha aparecido un personaje misterioso! ✨\n\n"
        f"{char['rarity']}\n\n"
        "🎲 Adivina quién es escribiendo su nombre en el chat\n"
        "o con /adivina <nombre>\n"
        f"⏰ Tienes {SPAWN_TIMEOUT // 60} minutos  •  💡 /pista para una pista"
    )
    try:
        msg = await context.bot.send_photo(chat_id=chat_id, photo=char["image_url"], caption=caption)
        _active[chat_id]["message_id"] = msg.message_id
    except Exception as e:
        logger.warning("No se pudo enviar la foto (%s), mando texto", e)
        msg = await context.bot.send_message(chat_id, caption + f"\n🖼️ {char['image_url']}")
        _active[chat_id]["message_id"] = msg.message_id
    return True


async def check_timeouts(context: ContextTypes.DEFAULT_TYPE):
    """Cada 30 s revisa spawns caducados y revela la respuesta."""
    now = time.time()
    expired = [cid for cid, s in _active.items() if now - s["spawned_at"] > SPAWN_TIMEOUT]
    for chat_id in expired:
        spawn = _active.pop(chat_id, None)
        if not spawn:
            continue
        char = spawn["character"]
        await context.bot.send_message(
            chat_id,
            "⏰ ¡Se acabó el tiempo! Nadie lo adivinó.\n\n"
            f"Era **{char['name']}** de *{char['anime']}* {char['rarity']}",
            parse_mode="Markdown",
        )


async def handle_correct_guess(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user):
    spawn = _active.pop(chat_id, None)
    if not spawn:
        return
    char = spawn["character"]
    uid = str(user.id)
    entry = _data.setdefault(uid, {"username": user.username or user.first_name, "points": 0, "characters": []})
    entry["username"] = user.username or user.first_name
    entry["points"] = int(entry.get("points", 0)) + char["points"]
    # Evitar duplicados exactos en la colección (se guarda igual la primera vez)
    if not any(c.get("name") == char["name"] for c in entry.get("characters", [])):
        entry.setdefault("characters", []).append({
            "name": char["name"],
            "anime": char["anime"],
            "rarity": char["rarity"],
            "image_url": char["image_url"],
            "caught_at": time.strftime("%Y-%m-%d"),
        })
    save_data()

    await update.effective_message.reply_text(
        f"🎉 ¡{user.first_name} lo adivinó!\n\n"
        f"Era **{char['name']}** de *{char['anime']}*\n"
        f"{char['rarity']}  •  +{char['points']} puntos\n\n"
        f"📦 {user.first_name} ya tiene {len(entry['characters'])} personaje(s). "
        "Mira tu colección con /coleccion",
        parse_mode="Markdown",
    )


async def try_guess(update: Update, context: ContextTypes.DEFAULT_TYPE, guess_text: str) -> bool:
    """Procesa un intento. Devuelve True si era el correcto."""
    chat_id = update.effective_chat.id
    spawn = _active.get(chat_id)
    if not spawn:
        return False

    user = update.effective_user
    # Anti-spam: 1 intento cada 2 segundos por usuario
    key = (chat_id, user.id)
    now = time.time()
    if now - _last_guess.get(key, 0) < 2:
        return False
    _last_guess[key] = now

    char = spawn["character"]
    if is_correct_guess(guess_text, char["name"]):
        await handle_correct_guess(update, context, chat_id, user)
        return True

    # Pista suave si estuvo muy cerca
    ratio = difflib.SequenceMatcher(None, normalize(guess_text), normalize(char["name"])).ratio()
    if ratio > 0.82:
        await update.effective_message.reply_text("🔥 ¡Casi! Estás muy cerca, inténtalo de nuevo.")
    return False


# ---------------------------------------------------------------- Comandos

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 ¡Hola! Soy el bot gacha de anime.\n\n"
        f"Cada {SPAWN_EVERY} mensajes en el grupo aparecerá un personaje misterioso "
        "con solo su imagen, sin nombre ni anime.\n"
        "Adivina quién es escribiendo su nombre y quédatelo.\n\n"
        "Comandos:\n"
        "/adivina <nombre> - intentar adivinar\n"
        "/pista - una pista del personaje activo\n"
        "/invocar - forzar que aparezca uno ahora\n"
        "/coleccion - tus personajes atrapados\n"
        "/top - ranking de puntos\n"
        "/ayuda - ver esto de nuevo"
    )


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def invocar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in _active:
        await update.message.reply_text("Ya hay un personaje activo esperando a ser adivinado 👀")
        return
    await spawn_character(context, chat_id)


async def adivina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Escribe: /adivina <nombre>  — por ejemplo: /adivina Luffy")
        return
    if update.effective_chat.id not in _active:
        await update.message.reply_text("Ahora mismo no hay ningún personaje activo. Habla en el grupo y aparecerá uno.")
        return
    await try_guess(update, context, " ".join(context.args))


async def pista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    spawn = _active.get(update.effective_chat.id)
    if not spawn:
        await update.message.reply_text("No hay personaje activo ahora.")
        return
    char = spawn["character"]
    name = char["name"]
    await update.message.reply_text(
        "💡 Pista:\n"
        f"• Nombre: {len(name)} letras, empieza con **{name[0]}**\n"
        f"• Anime: empieza con **{char['anime'][0]}**\n"
        f"• Rareza: {char['rarity']}",
        parse_mode="Markdown",
    )


async def coleccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    entry = _data.get(str(user.id))
    if not entry or not entry.get("characters"):
        await update.message.reply_text("📦 Aún no tienes personajes. ¡Adivina el próximo que aparezca!")
        return
    lines = [f"📦 Colección de {user.first_name} — {entry.get('points', 0)} puntos\n"]
    for c in entry["characters"][-20:]:
        lines.append(f"• {c['name']} — {c['anime']} {c['rarity']}")
    if len(entry["characters"]) > 20:
        lines.append(f"\n...y {len(entry['characters']) - 20} más.")
    await update.message.reply_text("\n".join(lines))


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _data:
        await update.message.reply_text("🏆 Aún no hay puntos. ¡Sé el primero en adivinar!")
        return
    ranking = sorted(_data.values(), key=lambda e: int(e.get("points", 0)), reverse=True)[:10]
    lines = ["🏆 Top gacha\n"]
    for i, e in enumerate(ranking, 1):
        lines.append(f"{i}. {e.get('username', '?')} — {e.get('points', 0)} pts ({len(e.get('characters', []))} personajes)")
    await update.message.reply_text("\n".join(lines))


async def config_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"⚙️ Config actual:\n• Un personaje cada {SPAWN_EVERY} mensajes\n"
        f"• Tiempo para adivinar: {SPAWN_TIMEOUT} s\n"
        "Para cambiarlo, edita SPAWN_EVERY en el archivo .env y reinicia el bot."
    )


# ---------------------------------------------------------------- Mensajes normales

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cuenta mensajes y, si hay spawn activo, trata el texto como intento."""
    msg = update.effective_message
    if not msg or not msg.text or update.effective_user.is_bot:
        return

    chat_id = update.effective_chat.id

    # Si hay un personaje activo, el mensaje es un intento de adivinanza.
    if chat_id in _active:
        await try_guess(update, context, msg.text)
        return

    # Si no, contar hacia el próximo spawn.
    _counters[chat_id] = _counters.get(chat_id, 0) + 1
    if _counters[chat_id] >= SPAWN_EVERY:
        await spawn_character(context, chat_id)


# ---------------------------------------------------------------- Main

def main():
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_TOKEN. Copia .env.example a .env y pon el token de BotFather.")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("help", ayuda))
    app.add_handler(CommandHandler("invocar", invocar))
    app.add_handler(CommandHandler("adivina", adivina))
    app.add_handler(CommandHandler("pista", pista))
    app.add_handler(CommandHandler("coleccion", coleccion))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("config", config_info))
    # Los mensajes de texto normales van después de los comandos.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    if app.job_queue:
        app.job_queue.run_repeating(check_timeouts, interval=30, first=30)

    logger.info("Bot gacha iniciado. Un personaje cada %s mensajes.", SPAWN_EVERY)
    app.run_polling()


if __name__ == "__main__":
    main()
