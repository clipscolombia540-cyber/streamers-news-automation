import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from scripts.tiktok import (
    convertir_fecha,
    descripcion_configuracion_feeds,
    filtrar_publicaciones_recientes,
    obtener_feeds,
)


class TikTokFilterTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)

    def item(self, url, title, date):
        return {
            "creador": "Westcol",
            "titulo": title,
            "enlace": url,
            "fecha": date,
        }

    def test_includes_verified_post_within_48_hours(self):
        fresh = self.item(
            "https://www.tiktok.com/@westcol/video/123",
            "Clip reciente",
            self.now - timedelta(hours=3),
        )
        results, diag = filtrar_publicaciones_recientes([[fresh]], self.now, 48)
        self.assertEqual(len(results), 1)
        self.assertEqual(diag["dentro_periodo"], 1)

    def test_excludes_old_post(self):
        old = self.item(
            "https://www.tiktok.com/@westcol/video/old",
            "Clip antiguo",
            self.now - timedelta(hours=49),
        )
        results, diag = filtrar_publicaciones_recientes([[old]], self.now, 48)
        self.assertEqual(results, [])
        self.assertEqual(diag["fuera_periodo_antiguas"], 1)

    def test_excludes_unknown_and_future_dates(self):
        unknown = self.item(
            "https://www.tiktok.com/@westcol/video/unknown",
            "Sin fecha",
            None,
        )
        future = self.item(
            "https://www.tiktok.com/@westcol/video/future",
            "Fecha futura",
            self.now + timedelta(minutes=5),
        )
        results, diag = filtrar_publicaciones_recientes([[unknown, future]], self.now, 48)
        self.assertEqual(results, [])
        self.assertEqual(diag["sin_fecha"], 1)
        self.assertEqual(diag["fecha_futura"], 1)

    def test_deduplicates_same_link(self):
        one = self.item(
            "https://www.tiktok.com/@westcol/video/123",
            "Clip",
            self.now - timedelta(hours=1),
        )
        duplicate = self.item(
            "https://www.tiktok.com/@westcol/video/123/",
            "Clip duplicado",
            self.now - timedelta(hours=2),
        )
        results, diag = filtrar_publicaciones_recientes([[one], [duplicate]], self.now, 48)
        self.assertEqual(len(results), 1)
        self.assertEqual(diag["duplicadas"], 1)

    def test_parses_iso_date(self):
        parsed = convertir_fecha("2026-10-10T10:00:00Z")
        self.assertEqual(parsed, datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc))

    def test_reads_multiple_feeds_from_environment(self):
        configuracion = (
            "Westcol=https://example.com/westcol.xml;"
            "Emergente=https://example.com/emergente.xml"
        )
        with patch.dict("os.environ", {"TIKTOK_FEEDS": configuracion}):
            feeds = obtener_feeds()
        self.assertEqual(len(feeds), 2)
        self.assertEqual(feeds["Emergente"], "https://example.com/emergente.xml")

    def test_reports_when_only_default_feed_is_used(self):
        with patch.dict("os.environ", {"TIKTOK_FEEDS": ""}):
            self.assertIn(
                "únicamente el feed predeterminado de Westcol",
                descripcion_configuracion_feeds(),
            )

    def test_reports_custom_feed_configuration(self):
        with patch.dict(
            "os.environ",
            {"TIKTOK_FEEDS": "Westcol=https://example.com/westcol.xml"},
        ):
            self.assertIn(
                "feeds personalizados",
                descripcion_configuracion_feeds(),
            )

    def test_invalid_environment_uses_default_feed(self):
        with patch.dict("os.environ", {"TIKTOK_FEEDS": "esto-no-es-un-feed"}):
            feeds = obtener_feeds()
        self.assertIn("Westcol", feeds)


if __name__ == "__main__":
    unittest.main()
