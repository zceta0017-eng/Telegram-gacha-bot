# Bot Gacha v3 — Lazos

Solo personajes **femeninos** de animes y videojuegos populares.
Pool: **200 personajes, 54 series** (126 de anime, 74 de videojuegos), en `characters.json`.

## Cómo funciona

- Cada **100 mensajes** del grupo aparece una chica al azar, **solo con su imagen**.
  Sin nombre, sin anime/videojuego y sin pistas.
- Se captura con **/vinculo** (también vale escribir `/vínculo`). La primera persona que lo escribe, gana.
- Dura **entre 5 y 10 mensajes**. Si nadie la captura, el bot revela quién era y de dónde venía, y ya no se puede capturar hasta que vuelva a salir.
- Rarezas de 1 a 5 estrellas. Probabilidad de spawn: ★ 40%, ★★ 30%, ★★★ 18%, ★★★★ 9%, ★★★★★ 3%. Más estrellas = más raro que salga.
- Puntos: ★ 10, ★★ 20, ★★★ 30, ★★★★ 50, ★★★★★ 100.
- Sin variantes por ahora: un personaje = una imagen. Es la versión simple para calar.

## Comandos

| Comando | Qué hace |
|---|---|
| `/vinculo` | Capturar al personaje activo (la primera persona gana) |
| `/lazos` | Ver tu colección, paginada por serie, en orden alfabético. Arriba, tu favorita con su foto |
| `/tributo <id>` | Donar un personaje. Responde al mensaje de esa persona y escribe `/tributo 2` |
| `/liberar <id>` | Eliminar un personaje tuyo (pide confirmación con botón) |
| `/pactar <id>` | Intercambiar. Responde al mensaje de la otra persona con `/pactar 178`. La otra persona responde al mensaje del bot con su ID, y los dos dan a ✅ Aceptar (solo ellos pueden pulsar). Caduca en 5 min |
| `/transmutar <id> <id> <id>` | Das 3 vínculos tuyos (repetidos o no) y sale un personaje al azar **solo para ti**, con 10-20 mensajes para capturarla. No interfiere con el spawn general. Los 3 que diste se pierden aunque no captures el nuevo. Si falla el spawn, se te devuelven los 3 |
| `/atesorar <id>` | Marcar tu **única** favorita (reemplaza la anterior). Sin número, muestra la actual. `/atesorar 0` la quita |
| `/podio` | Ranking del grupo (antes `/top`, sigue funcionando) |
| `/list` | Series que tiene el bot y cuántos personajes tiene cada una (paginado) |
| `/timepawn <n>` | **Solo admins.** Cada cuántos mensajes aparece un personaje (10 a 500). Sin número, muestra el actual. Antes se llamaba `/spawn_cada`, sigue funcionando |
| `/invocar` | **Solo admins.** Forzar que aparezca un personaje al azar, para probar |
| `/invocar <id>` | **Solo el propietario del grupo.** Forzar que aparezca ese personaje concreto por ID. Los admins con `/invocar` sin ID solo sacan al azar |
| `/start` / `/ayuda` | Reglas y comandos |

Nota sobre los comandos con acento: Telegram solo permite comandos sin acento en el menú, por eso el comando oficial es `/vinculo`. Si escribes `/vínculo` con acento, el bot también lo entiende como captura. Lo mismo con `/lazos`, `/tributo`, `/liberar`, `/pactar`, `/transmutar`, `/atesorar`, `/podio`, `/list`: funcionan en minúscula o con mayúscula inicial.

## /lazos — formato exacto

```
💞 Lazos de Edgar
Colección: 7 en total (4 distintos) · 650 puntos
Página 1/1

Genshin Impact 27/1
127. Klee [1]

Lycoris Recoil 3/2
1. Chisato Nishikigi [2]
2. Takina Inoue [1] ❤️
```

- `Colección: 7 en total (4 distintos)` = tamaño de colección, como el "Harem size" del bot de referencia.
- `Lycoris Recoil 3/2` = 3 personajes de esa serie en el bot / 2 distintos que tienes de esa serie.
- `2. Takina Inoue [1] ❤️` = ID 2, nombre, [copias que tienes], ❤️ si es tu favorita.
- Si tienes favorita marcada, **primero** sale su foto en el grupo, para que todos la vean, y debajo sale el listado.

Botones de /lazos (diseño propio, no copia del bot de referencia):
- `« Anterior` / `Siguiente »` para pasar página, `⏮️ Inicio` / `Fin ⏭️` para saltar al principio o al final.
- `Inline 🌐` abre la galería inline con tus ilustraciones.
- `✖️ Cerrar` cierra el listado.

Solo la persona que pidió /lazos puede pulsar esos botones. Si otro lo intenta, el bot le dice que esa colección no es suya.

## Botón Inline — cómo activarlo

1. En Telegram, abre **@BotFather**.
2. Escribe `/setinline`.
3. Elige tu bot.
4. Escribe un texto corto, por ejemplo: `Mira tus lazos`.
5. Vuelve a `/setinline` para cambiarlo si quieres, o déjalo así.

También quita la privacidad del grupo para que el bot vea los mensajes (si no, no cuenta los 100 mensajes):
1. En **@BotFather**, `/setprivacy` → elige tu bot → **Disable**.

Cómo se usa: en /lazos, pulsa **Inline 🌐**. Se abre una rejilla con tus ilustraciones, solo la ves tú, no se manda nada al grupo.
Ojo: ver la rejilla no manda nada; si **tocas** una foto de la rejilla, esa foto sí se envía al chat donde estás. Para solo ver, mira la rejilla y ciérrala con la X.

## /list — formato

```
📚 Series del bot
Total: 200 personajes · 54 series
Página 1/6

Attack on Titan — 4
Bocchi the Rock! — 3
...
```

## /pactar — flujo exacto

1. Tú ves el ID en /lazos, respondes un mensaje de la otra persona y escribes `/pactar 178`.
2. El bot publica el trueque y le dice a esa persona: responde a ESTE mensaje con `/pactar <tu ID>`.
3. El bot muestra los dos personajes y los botones ✅ Aceptar / ❌ Cancelar.
4. Solo los dos pueden pulsar. Cada uno tiene que dar a Aceptar; si uno cancela o pasan 5 minutos, se cancela y nadie pierde nada.
5. Cuando los dos aceptan, se intercambian.

Telegram no tiene una "pestaña" para escribir el ID, por eso la otra persona lo escribe respondiendo al mensaje del bot. Es lo más cercano que permite Telegram.

## /transmutar — flujo exacto

```
/transmutar 178 45 12
```

- Das 3 vínculos tuyos, repetidos o no. Si das tu única copia de uno, lo pierdes.
- El bot saca un personaje al azar **distinto de los 3 que diste**, con la misma rareza de siempre (★ 40%, ★★ 30%, ★★★ 18%, ★★★★ 9%, ★★★★★ 3%).
- Ese personaje sale en el grupo, solo con su imagen, y **solo tú** lo puedes capturar con /vinculo. Si otro lo intenta, el bot le dice que es solo tuyo.
- Dura **entre 10 y 20 mensajes** (al azar), para que un troll spameando no te quite el tiempo.
- **No interfiere con el spawn general**: son dos contadores aparte. El general sigue contando sus 100 mensajes y dura 5-10, y puede aparecer mientras tu transmutación está activa. Cuando escribes /vinculo, el bot primero revisa si tienes una transmutación activa y te da esa; si no, te da la general.
- Solo puede haber una transmutación activa por grupo a la vez.

## Agregar más personajes y series

No hay que tocar código. Solo añadir una línea en `characters.json`:

```json
{"id": 201, "name": "Nombre", "series": "Nombre del anime", "type": "Anime", "rarity": 4}
```

- El **ID no se puede repetir** y sigue el orden: 201, 202, 203...
- **No cambies el ID de un personaje que ya existe**, porque si alguien ya lo tiene, se le perdería.
- Si es una serie nueva, solo pones el nombre nuevo y el total se actualiza solo.
- Sube el `characters.json` nuevo a GitHub y Railway redeplega solo.

## Imágenes y derechos

Las imágenes **no son nuestras**. El bot no las guarda ni las vende: en cada spawn pide en vivo a Jikan (MyAnimeList) y, si falla, a AniList, la imagen de ese personaje, y la manda a Telegram. El arte es de sus autores/estudios. Si MyAnimeList o AniList quitan esa imagen, dejará de salir. Es para jugar en un grupo, sin vender nada.

## Instalar y desplegar

```bash
pip install -r requirements.txt
cp .env.example .env   # pon ahí tu TELEGRAM_TOKEN de BotFather, no lo compartas
python bot.py
```

En Railway: sube estos archivos a GitHub (ver GUIA_TELEFONO.md), pon en Variables `TELEGRAM_TOKEN` y `SPAWN_EVERY=100`, y añade el bot al grupo como admin. `runtime.txt` debe decir `python-3.12.13` (no 3.12.3, que falla en Railway).

## Archivos

- `bot.py` — el bot v3
- `characters.json` — pool de 200 personajes (IDs 1-200), 54 series
- `requirements.txt` — python-telegram-bot, requests, python-dotenv
- `Procfile`, `runtime.txt`, `render.yaml` — para Railway / Render
- `.env.example` — ejemplo de variables (sin el token real)
- `GUIA_TELEFONO.md` — guía desde el teléfono
