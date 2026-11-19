# Poner el bot en marcha desde el teléfono (Android)

Sí se puede, y hay 2 formas. La 2 es la recomendada.

## Opción 1: Directo en el teléfono con Termux (gratis, pero se apaga)

Termux es una app que te da una terminal en Android, como la ventana negra de la PC.

1. Instala **Termux** desde F-Droid (la de Play Store está desactualizada).
2. Ábrela y escribe, uno por uno:
   ```
   pkg install python -y
   pip install python-telegram-bot requests python-dotenv
   ```
3. Descarga los archivos del bot a tu teléfono y muévelos a la carpeta de Termux, o descárgalos dentro de Termux.
4. Edita el archivo `.env` y pega tu token de BotFather.
5. Arranca:
   ```
   python bot.py
   ```

**Pegas:** el bot solo funciona mientras Termux esté abierto y el teléfono encendido. Gasta batería y si cierras la app, se apaga. Sirve para probar, no para dejarlo 24/7.

## Opción 2: En la nube, desde el navegador del teléfono (recomendada)

Aquí el bot corre en un servidor, no en tu teléfono. Tu teléfono solo sirve para configurarlo una vez, y luego queda prendido 24/7 aunque apagues el teléfono.

### Con Railway (lo más fácil desde el móvil)

1. Crea una cuenta en GitHub desde el navegador del teléfono y sube esta carpeta (bot.py, requirements.txt, Procfile, runtime.txt).
2. Entra a railway.app y crea una cuenta (puedes entrar con GitHub).
3. New Project → Deploy from GitHub repo → elige el repo del bot.
4. En Variables, añade:
   - `TELEGRAM_TOKEN` = tu token de BotFather
   - `SPAWN_EVERY` = `100`
5. Railway detecta el `Procfile` y arranca solo con `python bot.py`.

### Con Render (alternativa)

1. Sube la carpeta a GitHub igual que arriba.
2. Entra a render.com → New → Background Worker → elige el repo.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python bot.py`
5. En Environment Variables añade `TELEGRAM_TOKEN` con tu token y `SPAWN_EVERY` = `100`.

El archivo `render.yaml` de esta carpeta ya trae esa configuración lista.

## Qué sí se hace 100% desde el teléfono sin PC

- Crear el bot con @BotFather y sacar el token: sí, desde Telegram.
- Añadir el bot a tu grupo y hacerlo admin: sí.
- Probar el bot con `/invocar`: sí.
- Subir los archivos a GitHub / Railway / Render: sí, desde Chrome en el teléfono.

Lo único que NO es cómodo desde el teléfono es editar archivos y escribir comandos largos, pero se puede con Termux o con el editor de GitHub.
