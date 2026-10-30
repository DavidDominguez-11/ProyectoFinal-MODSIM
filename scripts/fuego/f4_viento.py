"""Fase 4: viento horario ERA5 para el período simulado.

Se consulta el reanálisis ERA5 (Copernicus) a través del archivo histórico de
Open-Meteo, que no requiere clave. Se toma un solo punto en el centro del
corredor y se aplica como viento uniforme en el dominio: ERA5 tiene ~31 km
de resolución y no resuelve el viento canalizado en los cañones, por eso el
modelo incluye un factor de viento calibrable.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.parse
import urllib.request

from comun import PROCESADO, leer_dominio


URL = "https://archive-api.open-meteo.com/v1/archive"
PUNTO = {"lat": 39.78, "lon": -121.55}  # Entre Concow y Paradise.


def main() -> None:
    dominio = leer_dominio()
    ignicion = dt.datetime.fromisoformat(dominio["ignicion"]["hora_local"])
    fin = ignicion + dt.timedelta(minutes=dominio["horizonte_min"])
    parametros = {
        "latitude": PUNTO["lat"],
        "longitude": PUNTO["lon"],
        "start_date": ignicion.date().isoformat(),
        "end_date": fin.date().isoformat(),
        "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m",
        "wind_speed_unit": "ms",
        "timezone": dominio["ignicion"]["zona_horaria"],
        "models": "era5",
    }
    url = URL + "?" + urllib.parse.urlencode(parametros)
    with urllib.request.urlopen(url, timeout=60) as respuesta:
        datos = json.load(respuesta)

    horas = datos["hourly"]
    filas = []
    for i, texto in enumerate(horas["time"]):
        momento = dt.datetime.fromisoformat(texto)
        minuto = (momento - ignicion).total_seconds() / 60
        # Se conserva la hora previa a la ignición para interpolar desde el minuto 0.
        if -60 < minuto <= dominio["horizonte_min"] + 60:
            filas.append({
                "hora_local": texto,
                "minuto": round(minuto),
                "velocidad_ms": horas["wind_speed_10m"][i],
                "rafaga_ms": horas["wind_gusts_10m"][i],
                "direccion_desde_grados": horas["wind_direction_10m"][i],
                "humedad_relativa_pct": horas["relative_humidity_2m"][i],
            })

    PROCESADO.mkdir(parents=True, exist_ok=True)
    with open(PROCESADO / "viento_era5.csv", "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"Fuente: {url}")
    for fila in filas:
        print(fila)


if __name__ == "__main__":
    main()
