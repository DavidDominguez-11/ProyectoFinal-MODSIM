"""Verificación del autómata de fuego con grillas sintéticas pequeñas."""

import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "fuego"))

from modelo_fuego import Entradas, Parametros, simular  # noqa: E402


def entradas(clase=None, elevacion=None, velocidad=0.0, desde=0.0, horizonte=60.0) -> Entradas:
    clase = np.full((41, 41), 4, dtype=np.int8) if clase is None else clase
    elevacion = np.zeros(clase.shape) if elevacion is None else elevacion
    return Entradas(
        clase=clase, elevacion=elevacion, resolucion=100.0, ignicion=(20, 20),
        viento_minuto=np.array([0.0, 1000.0]),
        viento_velocidad=np.array([velocidad, velocidad]),
        viento_desde_grados=np.array([desde, desde]),
        horizonte_min=horizonte,
    )


SIN_FOCOS = Parametros(p_foco=0.0)


class ModeloFuegoTests(unittest.TestCase):
    def test_reproducible_con_semilla(self) -> None:
        a = simular(entradas(velocidad=5), Parametros(), semilla=7)
        b = simular(entradas(velocidad=5), Parametros(), semilla=7)
        np.testing.assert_array_equal(a, b)

    def test_ignicion_en_minuto_cero_y_tiempos_en_horizonte(self) -> None:
        llegada = simular(entradas(), SIN_FOCOS, semilla=1)
        self.assertEqual(llegada[20, 20], 0.0)
        quemadas = llegada[~np.isnan(llegada)]
        self.assertTrue(np.all((quemadas >= 0) & (quemadas <= 60)))

    def test_sin_combustible_no_se_propaga(self) -> None:
        clase = np.full((41, 41), -1, dtype=np.int8)
        clase[20, 20] = 4
        llegada = simular(entradas(clase=clase), Parametros(), semilla=1)
        self.assertEqual(int(np.sum(~np.isnan(llegada))), 1)

    def test_barrera_no_combustible_detiene_frente_sin_focos(self) -> None:
        clase = np.full((41, 41), 4, dtype=np.int8)
        clase[:, 25:27] = -1
        llegada = simular(entradas(clase=clase, horizonte=200), SIN_FOCOS, semilla=3)
        self.assertTrue(np.all(np.isnan(llegada[:, 27:])))

    def test_viento_favorece_la_direccion_a_sotavento(self) -> None:
        # Viento desde el oeste (270°): el fuego debe avanzar más hacia el este.
        llegada = simular(entradas(velocidad=8, desde=270, horizonte=15), SIN_FOCOS, semilla=2)
        quemadas = ~np.isnan(llegada)
        self.assertGreater(quemadas[:, 21:].sum(), 2 * quemadas[:, :20].sum())

    def test_pendiente_favorece_avance_cuesta_arriba(self) -> None:
        # Terreno que sube hacia el norte (filas menores).
        elevacion = np.tile(np.arange(41)[::-1, None] * 20.0, (1, 41))
        llegada = simular(entradas(elevacion=elevacion, horizonte=15), SIN_FOCOS, semilla=4)
        quemadas = ~np.isnan(llegada)
        self.assertGreater(quemadas[:20].sum(), quemadas[21:].sum())

    def test_focos_saltan_una_barrera(self) -> None:
        clase = np.full((41, 81), 4, dtype=np.int8)
        clase[:, 25:30] = -1
        ent = entradas(clase=clase, velocidad=8, desde=270, horizonte=120)
        focos = Parametros(p_foco=0.05, distancia_foco_m=600)
        saltos = [np.any(~np.isnan(simular(ent, focos, semilla=s)[:, 30:])) for s in range(5)]
        self.assertTrue(any(saltos))


if __name__ == "__main__":
    unittest.main()
