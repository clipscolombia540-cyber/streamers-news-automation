import unittest
from scripts.noticias import (
    es_noticia_promocional,
    generar_borrador_copy,
    parece_contenido_de_creadores,
    titulo_probablemente_en_ingles,
)


class FiltroEmergentesTests(unittest.TestCase):
    def test_descarta_noticia_comercial_de_porkcolombia(self):
        self.assertTrue(
            es_noticia_promocional(
                "Tulio Recomienda presenta campaña con Porkcolombia"
            )
        )

    def test_conserva_noticia_personal_sobre_influencer(self):
        self.assertFalse(
            es_noticia_promocional(
                "La Liendra responde a las críticas y cuenta qué pasó"
            )
        )

    def test_genera_copy_sin_asegurar_hechos_no_verificados(self):
        copy = generar_borrador_copy({
            "titulo": "La reacción de Westcol en directo",
            "creador": "Westcol",
            "categoria": "Clip de terceros",
            "canal": "Cuenta de clips",
            "url": "https://example.com/clip",
        })
        self.assertIn("Westcol", copy["gancho_a"])
        self.assertEqual(copy["titulo"], "La reacción de Westcol en directo")
        self.assertIn("permiso", copy["descripcion"].lower())
        self.assertTrue(copy["hashtags"].startswith("#StreamersColombia"))

    def test_copy_de_emergente_usa_hashtags_de_descubrimiento(self):
        copy = generar_borrador_copy({
            "titulo": "Clip de streamer nuevo",
            "creador": "Streamer nuevo",
            "categoria": "Emergente por verificar",
        })
        self.assertIn("#StreamerEmergente", copy["hashtags"])

    def test_descarta_pokemon_que_solo_menciona_kick(self):
        video = {
            "titulo": "ABRIMOS POKEMON TCG | Kick Stream",
            "canal": "PastyStreams and PassThor",
        }
        self.assertFalse(parece_contenido_de_creadores(video))

    def test_descarta_futbol_sin_senales_de_stream(self):
        video = {
            "titulo": "Colombia rolls over Peru 2-0 victory",
            "canal": "Canal de futbol",
        }
        self.assertFalse(parece_contenido_de_creadores(video))

    def test_acepta_clip_de_streamer_colombiano(self):
        video = {
            "titulo": "Clip de streamer colombiano en Kick",
            "canal": "Clips Colombia",
        }
        self.assertTrue(parece_contenido_de_creadores(video))

    def test_acepta_reaccion_de_streamer_colombiano(self):
        video = {
            "titulo": "Streamer colombiano reacciona en directo",
            "canal": "Momentos de Streamers",
        }
        self.assertTrue(parece_contenido_de_creadores(video))

    def test_detecta_titulo_claramente_en_ingles(self):
        self.assertTrue(
            titulo_probablemente_en_ingles(
                "Westcol wants to take my robot"
            )
        )

    def test_no_descarta_titulo_en_espanol(self):
        self.assertFalse(
            titulo_probablemente_en_ingles(
                "La reacción de Westcol cuando el robot lo golpea"
            )
        )

    def test_no_asume_ingles_por_nombre_corto(self):
        self.assertFalse(titulo_probablemente_en_ingles("Westcol vs Mr Stiven"))

    def test_no_descarta_por_dos_palabras_inglesas_ambiguas(self):
        self.assertFalse(titulo_probablemente_en_ingles("Westcol official video"))


if __name__ == "__main__":
    unittest.main()
