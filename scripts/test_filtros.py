import unittest
from scripts.noticias import (
    es_noticia_promocional,
    generar_borrador_copy,
    parece_contenido_de_creadores,
    es_relevante_para_radar,
    titulo_probablemente_en_ingles,
    seleccionar_clips,
    detectar_creador,
)


class FiltroEmergentesTests(unittest.TestCase):
    def test_busquedas_de_red_jaapz_incluyen_vods_y_grupo(self):
        from scripts.noticias import EMERGENTES
        self.assertIn("Parchando con el Jaap Kick", EMERGENTES)
        self.assertIn("Parchando con los reales streamer Colombia Kick", EMERGENTES)
        self.assertIn("Jaap_Z invitados directo Colombia", EMERGENTES)

    def test_detecta_creadores_relacionados_con_jaapz(self):
        self.assertEqual(
            detectar_creador({"titulo": "Noche de terror con Jaap", "canal": "ZaViel7"}),
            "ZaViel7",
        )
        self.assertEqual(
            detectar_creador({"titulo": "MonoCOL_R en directo", "canal": "Kick Colombia"}),
            "MonoCOL_R",
        )

    def test_detecta_jaapz_como_creador_vigilado(self):
        self.assertEqual(
            detectar_creador({
                "titulo": "Jaap_Z se va de IRL por Pasto",
                "canal": "Clips Colombia",
            }),
            "Jaapz",
        )

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

    def test_copy_de_cuenta_de_clips_detecta_creador_del_titulo(self):
        copy = generar_borrador_copy({
            "titulo": "MR STIVEN vs AMERICANO 4KT y PIRLO420 | PARTIDO por 1 MILLON",
            "creador": "Cuenta de clips: Pelusa Clips Tc",
            "categoria": "Cuenta de clips",
            "canal": "Pelusa Clips Tc",
        })
        self.assertIn("MrStivenTC", copy["gancho_a"])
        self.assertIn("MrStivenTC", copy["descripcion"])

    def test_selecciona_clips_de_terceros_antes_que_respaldo(self):
        recientes = {
            "titulo": "Video oficial de Westcol",
            "url": "https://example.com/oficial",
            "fecha": __import__("datetime").datetime(2026, 10, 10, 10, 0),
            "creador": "Westcol",
            "categoria": "Principal",
        }
        tercero = {
            "titulo": "Clip de Westcol publicado por fan",
            "url": "https://example.com/tercero",
            "fecha": __import__("datetime").datetime(2026, 10, 9, 10, 0),
            "creador": "Westcol",
            "categoria": "Clip de terceros",
        }
        seleccionados = seleccionar_clips([recientes, tercero])
        self.assertEqual(seleccionados[0]["categoria"], "Clip de terceros")

    def test_limita_clips_del_mismo_creador_aunque_sean_de_varias_cuentas(self):
        from datetime import datetime
        videos = []
        for i in range(5):
            videos.append({
                "titulo": "Momento viral de Westcol en directo numero {}".format(i),
                "url": "https://example.com/westcol-{}".format(i),
                "fecha": datetime(2026, 10, 9, 10, i),
                "creador": "Cuenta de clips: Fan {}".format(i),
                "categoria": "Cuenta de clips",
                "canal": "Fan Clips {}".format(i),
            })
        seleccionados = seleccionar_clips(videos)
        self.assertEqual(len(seleccionados), 3)


    def test_limita_dedsafio_para_dar_espacio_a_otros_temas(self):
        from datetime import datetime
        videos = []
        for i in range(6):
            videos.append({
                "titulo": "DEDsafio Minecraft momento epico numero {}".format(i),
                "url": "https://example.com/dedsafio-{}".format(i),
                "fecha": datetime(2026, 10, 9, 10, i),
                "creador": "Cuenta de clips: Canal {}".format(i),
                "categoria": "Cuenta de clips",
                "canal": "Canal Clips {}".format(i),
            })
        seleccionados = seleccionar_clips(videos)
        self.assertEqual(len(seleccionados), 3)

    def test_descarta_cuenta_de_clips_extranjera_sin_relacion_colombiana(self):
        video = {
            "titulo": "Una espectadora de Destiny se ve obligada a soportar esto",
            "canal": "Destiny DGG Clips",
        }
        self.assertFalse(es_relevante_para_radar(video))

    def test_acepta_cuenta_de_clips_que_menciona_streamer_vigilado(self):
        video = {
            "titulo": "Westcol se sorprende en pleno directo",
            "canal": "La w clips",
        }
        self.assertTrue(es_relevante_para_radar(video))

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
