import unittest
from datetime import datetime, timedelta, timezone

from scripts.tiktok import convertir_fecha, filtrar_publicaciones_recientes


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


if __name__ == "__main__":
    unittest.main()
