# Streamers News Automation

Radar automático de clips de streamers, creadores emergentes e influencers. Los informes se guardan en `borradores/`.

## Activar una cobertura más amplia de TikTok

El radar lee feeds RSS públicos y solo incluye publicaciones con fecha verificable dentro de las últimas 48 horas. **No rastrea todo TikTok**: los resultados dependen de las cuentas y feeds configurados. Actualmente existe un feed predeterminado de Westcol; si entrega publicaciones antiguas, hay que añadir feeds actualizados.

### 1. Crear feeds RSS de cuentas de TikTok

1. Abre [la guía de RSS.app para TikTok](https://help.rss.app/en/articles/8891118-how-to-create-rss-feeds-from-tiktok).
2. Crea un feed para cada perfil público que quieras vigilar y copia la URL RSS XML que te entregue el servicio.
3. Para este canal, empieza por cuentas de cliperos, fans y recortes que publiquen momentos de directos ajenos; luego agrega creadores emergentes y perfiles oficiales como respaldo. Busca cuentas reales y públicas relacionadas con **Westcol, MrStivenTC, Pelicanger, Samulx, Chanty, La Sapa y Lonche de Huevito**. También puedes añadir influencers como **La Liendra, Yina Calderón y El Mindo** si sus perfiles tienen feeds disponibles. Estos nombres son objetivos de búsqueda, no una afirmación de que todos tengan un feed disponible.
4. No uses URLs de ejemplo ni enlaces de perfiles como si fueran feeds RSS: el valor debe ser la URL XML generada por el servicio.

### 2. Guardar los feeds como secreto en GitHub

Desde el navegador del celular:

1. Entra al [repositorio](https://github.com/clipscolombia540-cyber/streamers-news-automation).
2. Abre **Settings → Secrets and variables → Actions**.
3. Pulsa **New repository secret**.
4. En **Name**, escribe exactamente `TIKTOK_FEEDS`.
5. En **Secret**, pega los nombres y URLs reales, separados por punto y coma, con este formato ilustrativo:

   ```text
   Clipero:LaWClips=https://URL-RSS-REAL-1.xml;Fan:ClipsMrStiven=https://URL-RSS-REAL-2.xml;Emergente:NuevoStreamer=https://URL-RSS-REAL-3.xml;Streamer:Westcol=https://URL-RSS-REAL-4.xml
   ```

   Reemplaza todas las direcciones de ejemplo por URLs XML reales. Puedes añadir más pares `Etiqueta:Nombre=URL` usando el mismo separador. Las etiquetas `Clipero:`, `Clips:`, `Fan:`, `Momentos:` y `Recortes:` hacen que esos feeds aparezcan primero en el informe; `Emergente:` e `Influencer:` los clasifican por separado. No inventes URLs: usa únicamente las que genere el proveedor RSS.

6. Guarda el secreto y entra en **Actions → Radar de creadores y TikTok → Run workflow** para ejecutar una prueba manual.

### 3. Revisar el resultado

- [Radar de clips de TikTok](https://github.com/clipscolombia540-cyber/streamers-news-automation/blob/main/borradores/clips_tiktok.md)
- [Radar general de creadores y clips](https://github.com/clipscolombia540-cyber/streamers-news-automation/blob/main/borradores/radar_creadores.md)
- [Ejecuciones del radar](https://github.com/clipscolombia540-cyber/streamers-news-automation/actions)

El informe muestra cuántos feeds se consultaron, publicaciones leídas y cuántas tenían fecha verificable en las últimas 48 horas. Si todos los posts son antiguos, revisa si el proveedor RSS sigue actualizando ese feed o genera uno nuevo.

**Importante:** el informe es una lista de candidatos, no una autorización para republicar. Verifica el video completo, el contexto, las reglas de la plataforma y los permisos correspondientes antes de publicar.


## Publicar automáticamente en YouTube Shorts y TikTok

El workflow `.github/workflows/publicar.yml` automatiza la carga del archivo y la publicación en las dos plataformas. La primera versión se ejecuta manualmente desde GitHub Actions; no publica por su cuenta los enlaces del radar porque esos enlaces no son archivos editados ni implican permiso para reutilizar el contenido.

### Preparar secretos de GitHub

Abre **Settings → Secrets and variables → Actions → New repository secret**. Crea los secretos necesarios:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`
- `TIKTOK_ACCESS_TOKEN`

Para YouTube, configura un proyecto en [Google Cloud Console](https://console.cloud.google.com/), habilita **YouTube Data API v3**, configura OAuth para el canal correcto y genera un refresh token con el alcance `https://www.googleapis.com/auth/youtube.upload`. No uses una cuenta de servicio para YouTube.

Para TikTok, registra una aplicación en [TikTok for Developers](https://developers.tiktok.com/), agrega **Content Posting API**, consigue aprobación para `video.publish` y autoriza la cuenta que va a publicar. TikTok restringe a privado el contenido publicado por clientes que todavía no hayan pasado su auditoría; la publicación pública depende de esa aprobación. El token de TikTok puede caducar y deberá renovarse cuando corresponda.

**Nunca pegues tokens, contraseñas ni secretos en el código, en los informes o en este chat.** Guárdalos únicamente en GitHub Secrets.

### Ejecutar una publicación de prueba

1. Prepara un MP4 vertical 9:16 con edición, subtítulos y aporte original; utiliza material propio o con permiso explícito.
2. Hospeda el archivo en una URL HTTPS directa al MP4 que GitHub Actions pueda descargar. No uses la página de un video de YouTube o TikTok como `VIDEO_URL`.
3. Abre **Actions → Publicar video en YouTube Shorts y TikTok → Run workflow**.
4. Introduce la URL, título, descripción y hashtags.
5. Para la primera prueba, deja YouTube en `private` y TikTok en `SELF_ONLY`; marca la confirmación de derechos solo si realmente tienes autorización.
6. Ejecuta el workflow y revisa el resultado en cada cuenta antes de cambiar la privacidad a pública.

El publicador limita la descarga a 250 MB por video. Esta primera versión no crea ni edita videos a partir de los candidatos del radar, no programa publicaciones futuras y no salta las aprobaciones de las plataformas. La selección de material autorizado y la URL del MP4 siguen siendo entradas necesarias.
