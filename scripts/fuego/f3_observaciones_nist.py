"""Fase 3: limpia las observaciones del fuego de NIST (TN 2135, Appendix F).

Reglas documentadas, aplicadas en este orden:
1. Año: todas las filas dicen 2021; se sustituye por 2018 conservando mes y
   día (8 o 9 de noviembre). Justificación: el registro 911-001-1 coincide en
   identificador y hora con la primera llamada de 2018 en NIST TN 2252, tabla 10.
2. Duplicados: las hojas comparten filas; se deduplica por (fuente, fecha,
   hora, latitud, longitud, tipo), no solo por fuente.
3. Se excluyen observaciones con ventana de tiempo mayor a 60 min (hora
   imprecisa), fuego residual (columna "Residual Fire?" = x) y el tipo O,
   que mezcla observaciones indirectas (brasas cayendo, resplandor, humo).
   Significado de tipos inferido de las descripciones: V vegetación,
   S foco adelantado, R estructura residencial, C estructura comercial.
4. Llegada observada por celda: la hora mínima de las observaciones de la
   celda. Es una cota superior de la llegada real (el fuego pudo llegar antes).
5. Partición calibración/validación por bloques espaciales de 2 km: los
   bloques se barajan con semilla fija y cada uno va al conjunto con menos
   celdas, para que celdas vecinas no queden en ambos y los tamaños se parezcan.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import urllib.request

import numpy as np
import openpyxl
from pyproj import Transformer

from comun import CRUDO, PROCESADO, grilla_dominio, leer_dominio


URL = (
    "https://data.nist.gov/od/ds/mds2-2954/"
    "NIST%20TN%202135%20Appendix%20F%20Fire%20Spread%20Data.xlsx"
)
TIPOS_USADOS = {"V", "S", "R", "C"}
VENTANA_MAXIMA_MIN = 60
BLOQUE_M = 2000
SEMILLA_PARTICION = 2018


def descargar() -> bytes:
    destino = CRUDO / "nist_appendix_f.xlsx"
    if not destino.exists():
        CRUDO.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=90) as respuesta:
            destino.write_bytes(respuesta.read())
    return destino.read_bytes()


def main() -> None:
    contenido = descargar()
    dominio = leer_dominio()
    grilla = grilla_dominio(dominio)
    ignicion = dt.datetime.fromisoformat(dominio["ignicion"]["hora_local"])
    horizonte = dominio["horizonte_min"]
    a_utm = Transformer.from_crs("EPSG:4326", grilla.crs, always_xy=True)

    libro = openpyxl.load_workbook(CRUDO / "nist_appendix_f.xlsx", read_only=True, data_only=True)
    unicas: dict[tuple, tuple] = {}
    filas_totales = 0
    for hoja in libro:
        for fila in hoja.iter_rows(min_row=2, values_only=True):
            if not fila or fila[0] is None:
                continue
            filas_totales += 1
            clave = (fila[0], fila[1], fila[2], fila[5], fila[6], fila[10])
            unicas.setdefault(clave, fila)

    descartes = {"sin_hora_o_coordenada": 0, "ventana_mayor_60": 0, "residual": 0, "tipo_O_u_otro": 0,
                 "fuera_de_dominio": 0, "fuera_de_horizonte": 0}
    observaciones = []
    for fila in unicas.values():
        fuente, fecha, hora, _, ventana, lat, lon = fila[:7]
        tipo, residual = fila[10], fila[11]
        if not hasattr(fecha, "day") or not hasattr(hora, "hour") or not isinstance(lat, float):
            descartes["sin_hora_o_coordenada"] += 1
            continue
        if (ventana or 0) > VENTANA_MAXIMA_MIN:
            descartes["ventana_mayor_60"] += 1
            continue
        if residual:
            descartes["residual"] += 1
            continue
        if tipo not in TIPOS_USADOS:
            descartes["tipo_O_u_otro"] += 1
            continue
        momento = dt.datetime(2018, fecha.month, fecha.day, hora.hour, hora.minute)
        minuto = (momento - ignicion).total_seconds() / 60
        if not 0 <= minuto <= horizonte:
            descartes["fuera_de_horizonte"] += 1
            continue
        x, y = a_utm.transform(lon, lat)
        celda = grilla.celda(x, y)
        if celda is None:
            descartes["fuera_de_dominio"] += 1
            continue
        observaciones.append({
            "fuente": fuente, "hora_local": momento.isoformat(timespec="minutes"),
            "minuto": round(minuto), "ventana_min": ventana or 0, "tipo": tipo,
            "lat": lat, "lon": lon, "x": round(x, 1), "y": round(y, 1),
            "fila": celda[0], "col": celda[1],
        })

    # Llegada observada por celda: la observación más temprana.
    celdas: dict[tuple[int, int], dict] = {}
    for obs in observaciones:
        clave = (obs["fila"], obs["col"])
        actual = celdas.get(clave)
        if actual is None or obs["minuto"] < actual["minuto_llegada_obs"]:
            celdas[clave] = {
                "fila": clave[0], "col": clave[1], "minuto_llegada_obs": obs["minuto"],
                "ventana_min": obs["ventana_min"], "tipo": obs["tipo"], "fuente": obs["fuente"],
            }

    # Partición por bloques espaciales, balanceada por número de celdas.
    lado = BLOQUE_M / grilla.resolucion
    bloques: dict[tuple[int, int], list[dict]] = {}
    for celda in celdas.values():
        bloques.setdefault((int(celda["fila"] // lado), int(celda["col"] // lado)), []).append(celda)
    orden = list(bloques)
    np.random.default_rng(SEMILLA_PARTICION).shuffle(orden)
    tamanos = {"calibracion": 0, "validacion": 0}
    for bloque in orden:
        conjunto = min(tamanos, key=tamanos.get)
        for celda in bloques[bloque]:
            celda["conjunto"] = conjunto
        tamanos[conjunto] += len(bloques[bloque])

    PROCESADO.mkdir(parents=True, exist_ok=True)
    for nombre, filas in [("observaciones_nist.csv", observaciones),
                          ("llegada_observada_celdas.csv", sorted(celdas.values(),
                                                                  key=lambda c: c["minuto_llegada_obs"]))]:
        with open(PROCESADO / nombre, "w", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
            escritor.writeheader()
            escritor.writerows(filas)

    conjuntos = [c["conjunto"] for c in celdas.values()]
    resumen = {
        "fuente": URL,
        "sha256": hashlib.sha256(contenido).hexdigest(),
        "apariciones_de_filas": filas_totales,
        "observaciones_unicas": len(unicas),
        "descartes": descartes,
        "observaciones_usadas": len(observaciones),
        "por_tipo": {t: sum(o["tipo"] == t for o in observaciones) for t in sorted(TIPOS_USADOS)},
        "celdas_con_llegada_observada": len(celdas),
        "celdas_calibracion": conjuntos.count("calibracion"),
        "celdas_validacion": conjuntos.count("validacion"),
        "rango_minutos": [min(o["minuto"] for o in observaciones),
                          max(o["minuto"] for o in observaciones)],
    }
    (PROCESADO / "observaciones_nist_resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
