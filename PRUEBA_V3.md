# Probar la v3 en 2 minutos (después de subirla a GitHub y que Railway redeplegue)

Haz esto en el grupo donde está el bot, con el bot ya como admin.

## 1. ¿Arrancó?
En Railway → Deployments → View Logs debe decir `Bot gacha iniciado`.
Si dice FAILED en "Build image", revisa que `runtime.txt` en GitHub diga `python-3.12.13`.

## 2. Prueba rápida, en este orden
1. `/invocar` — debe salir una imagen sola, sin nombre ni serie.
2. `/vinculo` — tú la capturas; el bot debe decirte quién era, su serie y sus estrellas.
3. `/lazos` — debe salir tu colección con el formato `Serie total/tuyos` y `ID. Nombre [cantidad]`, y arriba `Colección: X en total (Y distintos)`.
4. `/list` — debe decir `Total: 200 personajes · 54 series`.
5. `/timepawn` (sin número) — debe decir cada cuánto spawnea ahora; debe ser 100.

## 3. Si algo no responde
- Revisa en BotFather `/setprivacy` → Disable (si no, el bot no cuenta los 100 mensajes).
- Para el botón Inline 🌐 en /lazos, en BotFather `/setinline` y pon un texto corto, por ejemplo `Mira tus lazos`.
- Si Railway te vuelve a pedir $5 o dice que no quedan proyectos gratis, NO pagues todavía: borra un proyecto fallido (`amused-cooperation` o `steadfast-transformation`) y reintenta una sola vez con el token ya puesto en Variables antes de desplegar.
- Koyeb no es buen plan B para este bot tal como está: su instancia gratis no permite servicios tipo Worker y se duerme tras 1 hora sin tráfico web, y este bot usa polling (no tiene servidor web). No pierdas tiempo ahí.

## 4. Ojo con las colecciones
Las colecciones se guardan en `data.json` dentro del servidor. Si Railway redeplega desde cero, las colecciones pueden perderse. Para la prueba está bien; si el grupo ya juega en serio, avísame y lo pasamos a una base de datos que no se borre.
