import unittest
from scripts.noticias import parece_contenido_de_creadores, titulo_probablemente_en_ingles


class FiltroEmergentesTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
