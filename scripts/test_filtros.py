import unittest
from scripts.noticias import parece_contenido_de_creadores


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


if __name__ == "__main__":
    unittest.main()
