# Bot Gacha de Anime para Telegram

Cada ciertos mensajes en el grupo aparece un personaje misterioso: solo su imagen, **sin nombre y sin anime**. Quien lo adivine primero se lo queda.

## Cómo funciona

- Cada **20 mensajes** (cambiable) aparece un personaje al azar.
- El mensaje solo muestra la foto y su rareza: ⭐ Común, ⭐⭐⭐ Raro, ⭐⭐⭐⭐ Épico, ⭐⭐⭐⭐⭐ Legendario.
- Para adivinar, escribe el nombre en el chat o usa `/adivina <nombre>`. Vale el nombre completo, solo el nombre o solo el apellido: `Luffy`, `Monkey D. Luffy`.
- Si nadie acierta en 3 minutos, el bot revela quién era.
- Puntos por rareza: Común 10, Raro 25, Épico 50, Legendario 100.
- Las colecciones y puntos se guardan en `data.json`.

Las imágenes salen de la API gratuita de Jikan (MyAnimeList), sin clave. A veces usa una imagen variada del personaje, tipo fanart, desde `/characters/{id}/pictures`.

## Comandos

| Comando | Qué hace |
|---|---|
| `/start` / `/ayuda` | Bienvenida y lista de comandos |
| `/adivina <nombre>` | Intentar adivinar el personaje activo |
| `/pista` | Primera letra del nombre y del anime, y nº de letras |
| `/invocar` | Forzar que aparezca un personaje ahora (para probar) |
| `/coleccion` | Tus personajes atrapados y tus puntos |
| `/top` | Ranking de puntos del grupo |
| `/config` | Ver cada cuántos mensajes aparece |

También puedes adivinar simplemente escribiendo el nombre en el chat mientras haya un personaje activo.

## Ponerlo en marcha en 5 minutos

### 1. Crea el bot en Telegram
1. Abre Telegram y busca **@BotFather**.
2. Manda `/newbot`, ponle un nombre y un usuario que termine en `bot` (ej. `mi_gacha_bot`).
3. BotFather te dará un token como `123456:ABC...`. Guárdalo.

### 2. Añade el bot a tu grupo
1. En el grupo, toca el nombre del grupo → Añadir miembros → busca tu bot.
2. Hazlo administrador (o al menos dale permiso para leer mensajes, si no, no contará los mensajes ni verá las adivinanzas).
3. **Importante:** si el grupo tiene activado el modo de privacidad, el bot solo ve comandos. Para un bot de grupo, en @BotFather usa `/setprivacy` → elige tu bot → **Disable**. Así ve todos los mensajes y puede contarlos.

### 3. Instala y arranca el bot
```bash
# En la carpeta del bot
pip install -r requirements.txt
cp .env.example .env
# Edita .env y pega tu TELEGRAM_TOKEN
python bot.py
```

Deja la terminal abierta mientras quieras que el bot esté activo. Para que esté 24/7, súbelo a un hosting como Railway, Render o un VPS y arranca `python bot.py` allí (ver abajo).

### 4. Prueba
En el grupo manda `/invocar` y debería aparecer un personaje con solo su imagen. Adivínalo con su nombre.

## Cambiar cada cuántos mensajes aparece

En el archivo `.env`, cambia `SPAWN_EVERY`:

```
SPAWN_EVERY=10    # aparece cada 10 mensajes
SPAWN_EVERY=50    # aparece cada 50 mensajes
```

Guarda y reinicia el bot (`Ctrl+C` y `python bot.py` de nuevo).

## Para tenerlo 24/7 (opcional)

Opción fácil: **Railway / Render**
1. Sube esta carpeta a GitHub.
2. En Railway/Render crea un proyecto desde ese repo.
3. Pon la variable de entorno `TELEGRAM_TOKEN` con tu token (y `SPAWN_EVERY` si quieres).
4. Comando de inicio: `python bot.py`.

Opción en tu PC/servidor: usa `nohup python bot.py &` o un servicio systemd, y `data.json` guardará las colecciones.

## Archivos

- `bot.py` — todo el bot.
- `requirements.txt` — dependencias.
- `.env.example` — plantilla de configuración. No subas tu `.env` real a GitHub.
- `data.json` — se crea solo al atrapar el primer personaje.
