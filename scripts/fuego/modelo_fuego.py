"""Autómata celular estocástico de propagación del fuego.

Base: Alexandridis et al. (2008), "A cellular automata model for forest fire
spread prediction: the case of the wildfire that swept through Spetses Island
in 1990", Applied Mathematics and Computation 204(1), 191-201.

Una celda susceptible se enciende en un paso con probabilidad, por cada vecina
ardiendo (vecindad de Moore):

    p = p_h * (1 + p_veg) * p_w * p_s
    p_w = exp(c1 * V) * exp(V * c2 * (cos(theta) - 1))
    p_s = exp(a * theta_s)

V es la velocidad del viento (m/s), theta el ángulo entre el viento y la
dirección de propagación, theta_s la pendiente del terreno (grados) en esa
dirección. Se añade un mecanismo de focos adelantados (spotting), documentado
por NIST para el Camp Fire: cada celda ardiendo emite una brasa con
probabilidad p_foco por minuto, que cae a una distancia lognormal a favor del
viento y enciende la celda de destino con probabilidad p_ignicion_foco*(1+p_veg).

Estados: -1 no combustible, 0 susceptible, 1 ardiendo, 2 consumida.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field, replace
import json

import numpy as np

from comun import CONFIG, PROCESADO, grilla_dominio, leer_dominio


NO_COMBUSTIBLE, SUSCEPTIBLE, ARDIENDO, CONSUMIDA = -1, 0, 1, 2
# (desplazamiento fila, desplazamiento columna) de la vecina que transmite.
VECINAS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


@dataclass(frozen=True)
class Parametros:
    # Valores iniciales de Alexandridis et al. (2008); se recalibran en la fase 6.
    p_h: float = 0.58
    c1: float = 0.045
    c2: float = 0.131
    a_pendiente: float = 0.078
    # p_veg por clase: urbano, GR, GS, SH, TU, TL, SB (ver f2_preparar_grilla.CLASES).
    p_veg: tuple[float, ...] = (-0.3, 0.4, 0.3, 0.4, 0.2, -0.2, 0.0)
    factor_viento: float = 1.0
    duracion_min: float = 10.0
    p_foco: float = 0.002
    distancia_foco_m: float = 400.0
    sigma_foco: float = 0.8
    p_ignicion_foco: float = 0.4
    dispersion_foco_grados: float = 15.0
    paso_min: float = 1.0

    def con(self, **cambios) -> "Parametros":
        return replace(self, **cambios)


@dataclass
class Entradas:
    clase: np.ndarray
    elevacion: np.ndarray
    resolucion: float
    ignicion: tuple[int, int]
    viento_minuto: np.ndarray
    viento_velocidad: np.ndarray
    viento_desde_grados: np.ndarray
    horizonte_min: float
    extra: dict = field(default_factory=dict)


def simular(entradas: Entradas, parametros: Parametros, semilla: int) -> np.ndarray:
    """Devuelve el minuto de ignición de cada celda (NaN si no ardió)."""
    rng = np.random.default_rng(semilla)
    clase = entradas.clase
    filas, columnas = clase.shape
    res = entradas.resolucion
    paso = parametros.paso_min

    estado = np.where(clase >= 0, SUSCEPTIBLE, NO_COMBUSTIBLE).astype(np.int8)
    llegada = np.full(clase.shape, np.nan, dtype=np.float32)
    p_veg = np.asarray(parametros.p_veg)[np.clip(clase, 0, None)]
    factor_combustible = np.where(clase >= 0, parametros.p_h * (1 + p_veg), 0.0)

    # Término estático por vecina: combustible del destino y pendiente.
    elevacion = np.pad(entradas.elevacion, 1, mode="edge")
    base, direcciones = [], []
    for df, dc in VECINAS:
        origen = elevacion[1 + df:1 + df + filas, 1 + dc:1 + dc + columnas]
        distancia = res * np.hypot(df, dc)
        theta_s = np.degrees(np.arctan((entradas.elevacion - origen) / distancia))
        base.append(factor_combustible * np.exp(parametros.a_pendiente * theta_s))
        # Dirección de propagación origen -> destino en (este, norte).
        este, norte = -dc, df
        direcciones.append(np.array([este, norte]) / np.hypot(este, norte))

    estado[entradas.ignicion] = ARDIENDO
    llegada[entradas.ignicion] = 0.0
    pasos = int(round(entradas.horizonte_min / paso))
    for n in range(1, pasos + 1):
        minuto = n * paso
        velocidad = parametros.factor_viento * np.interp(
            minuto, entradas.viento_minuto, entradas.viento_velocidad)
        desde = np.radians(np.interp(minuto, entradas.viento_minuto, entradas.viento_desde_grados))
        hacia = np.array([-np.sin(desde), -np.cos(desde)])

        ardiendo = np.pad(estado == ARDIENDO, 1)
        sin_ignicion = np.ones(clase.shape)
        for (df, dc), b, d in zip(VECINAS, base, direcciones):
            cos_theta = float(d @ hacia)
            p_w = np.exp(parametros.c1 * velocidad) * np.exp(
                velocidad * parametros.c2 * (cos_theta - 1))
            vecina_ardiendo = ardiendo[1 + df:1 + df + filas, 1 + dc:1 + dc + columnas]
            # p está definida por minuto; un paso de "paso" minutos acumula esa probabilidad.
            p = 1.0 - (1.0 - np.clip(b * p_w, 0.0, 1.0)) ** paso
            sin_ignicion *= np.where(vecina_ardiendo, 1.0 - p, 1.0)
        nuevas = (estado == SUSCEPTIBLE) & (rng.random(clase.shape) < 1.0 - sin_ignicion)

        # Focos adelantados desde las celdas que ya ardían al inicio del paso.
        fuentes = np.argwhere(estado == ARDIENDO)
        emiten = fuentes[rng.random(len(fuentes)) < parametros.p_foco * paso]
        if len(emiten):
            escala = parametros.distancia_foco_m * max(velocidad, 0.1) / 5.0
            distancia = rng.lognormal(np.log(escala), parametros.sigma_foco, len(emiten))
            angulo = np.arctan2(hacia[1], hacia[0]) + np.radians(
                rng.normal(0, parametros.dispersion_foco_grados, len(emiten)))
            destino_f = np.round(emiten[:, 0] - distancia * np.sin(angulo) / res).astype(int)
            destino_c = np.round(emiten[:, 1] + distancia * np.cos(angulo) / res).astype(int)
            dentro = (destino_f >= 0) & (destino_f < filas) & (destino_c >= 0) & (destino_c < columnas)
            destino_f, destino_c = destino_f[dentro], destino_c[dentro]
            p_destino = parametros.p_ignicion_foco * (1 + p_veg[destino_f, destino_c])
            prende = (estado[destino_f, destino_c] == SUSCEPTIBLE) & (
                rng.random(len(destino_f)) < p_destino)
            nuevas[destino_f[prende], destino_c[prende]] = True

        consumidas = (estado == ARDIENDO) & (minuto - llegada >= parametros.duracion_min)
        estado[consumidas] = CONSUMIDA
        estado[nuevas] = ARDIENDO
        llegada[nuevas] = minuto
    return llegada


def cargar_parametros(nombre: str = "parametros_fuego.json") -> Parametros:
    ruta = CONFIG / nombre
    if not ruta.exists():
        return Parametros()
    datos = json.loads(ruta.read_text(encoding="utf-8"))["parametros"]
    datos["p_veg"] = tuple(datos["p_veg"])
    return Parametros(**datos)


def guardar_parametros(parametros: Parametros, nota: dict, nombre: str = "parametros_fuego.json") -> None:
    contenido = {"parametros": asdict(parametros), **nota}
    (CONFIG / nombre).write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")


def cargar_entradas() -> Entradas:
    """Lee la grilla de la fase 2, el viento de la fase 4 y la ignición del dominio."""
    from pyproj import Transformer

    dominio = leer_dominio()
    grilla = grilla_dominio(dominio)
    capas = np.load(PROCESADO / "grilla_fuego.npz")
    with open(PROCESADO / "viento_era5.csv", encoding="utf-8") as archivo:
        viento = list(csv.DictReader(archivo))
    x, y = Transformer.from_crs("EPSG:4326", grilla.crs, always_xy=True).transform(
        dominio["ignicion"]["lon"], dominio["ignicion"]["lat"])
    return Entradas(
        clase=capas["clase"],
        elevacion=capas["elevacion_m"].astype(np.float64),
        resolucion=grilla.resolucion,
        ignicion=grilla.celda(x, y),
        viento_minuto=np.array([float(v["minuto"]) for v in viento]),
        viento_velocidad=np.array([float(v["velocidad_ms"]) for v in viento]),
        viento_desde_grados=np.unwrap(
            np.array([float(v["direccion_desde_grados"]) for v in viento]), period=360),
        horizonte_min=dominio["horizonte_min"],
        extra={"grilla": grilla, "poblacion": capas["poblacion"],
               "dentro_perimetro": capas["dentro_perimetro"],
               "mascara_paradise": capas["mascara_paradise"]},
    )
