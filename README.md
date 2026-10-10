# Streamers News Automation

Radar automático de clips de streamers, creadores emergentes e influencers. Los informes se guardan en `borradores/`.

## Activar una cobertura más amplia de TikTok

El radar lee feeds RSS públicos y solo incluye publicaciones con fecha verificable dentro de las últimas 48 horas. **No rastrea todo TikTok**: los resultados dependen de las cuentas y feeds configurados. Actualmente existe un feed predeterminado de Westcol; si entrega publicaciones antiguas, hay que añadir feeds actualizados.

### 1. Crear feeds RSS de cuentas de TikTok

1. Abre [la guía de RSS.app para TikTok](https://help.rss.app/en/articles/8891118-how-to-create-rss-feeds-from-tiktok).
2. Crea un feed para cada perfil público que quieras vigilar y copia la URL RSS XML que te entregue el servicio.
3. Empieza con cuentas conocidas y luego agrega creadores emergentes. Lista sugerida para buscar sus perfiles oficiales en TikTok: **Westcol, MrStivenTC, Pelicanger, Samulx, Chanty, La Sapa y Lonche de Huevito**. Añade influencers como **La Liendra, Yina Calderón y El Mindo** si sus perfiles tienen feeds disponibles.
4. No uses URLs de ejemplo ni enlaces de perfiles como si fueran feeds RSS: el valor debe ser la URL XML generada por el servicio.

### 2. Guardar los feeds como secreto en GitHub

Desde el navegador del celular:

1. Entra al [repositorio](https://github.com/clipscolombia540-cyber/streamers-news-automation).
2. Abre **Settings → Secrets and variables → Actions**.
3. Pulsa **New repository secret**.
4. En **Name**, escribe exactamente `TIKTOK_FEEDS`.
5. En **Secret**, pega los nombres y URLs reales, separados por punto y coma, con este formato ilustrativo:

   ```text
   Westcol=https://URL-RSS-REAL-1.xml;MrStivenTC=https://URL-RSS-REAL-2.xml;Pelicanger=https://URL-RSS-REAL-3.xml
   ```

   Reemplaza todas las direcciones de ejemplo por URLs XML reales. Puedes añadir más pares `Nombre=URL` usando el mismo separador.

6. Guarda el secreto y entra en **Actions → Radar de creadores y TikTok → Run workflow** para ejecutar una prueba manual.

### 3. Revisar el resultado

- [Radar de clips de TikTok](https://github.com/clipscolombia540-cyber/streamers-news-automation/blob/main/borradores/clips_tiktok.md)
- [Radar general de creadores y clips](https://github.com/clipscolombia540-cyber/streamers-news-automation/blob/main/borradores/radar_creadores.md)
- [Ejecuciones del radar](https://github.com/clipscolombia540-cyber/streamers-news-automation/actions)

El informe muestra cuántos feeds se consultaron, publicaciones leídas y cuántas tenían fecha verificable en las últimas 48 horas. Si todos los posts son antiguos, revisa si el proveedor RSS sigue actualizando ese feed o genera uno nuevo.

**Importante:** el informe es una lista de candidatos, no una autorización para republicar. Verifica el video completo, el contexto, las reglas de la plataforma y los permisos correspondientes antes de publicar.
