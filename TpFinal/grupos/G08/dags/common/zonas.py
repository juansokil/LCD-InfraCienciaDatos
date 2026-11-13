"""
Zonas por coordenadas: point-in-polygon con shapely (sin PostGIS).

Una capa GeoJSON por red; la estacion que no cae en ningun poligono (o la red
sin capa) queda con la ciudad como zona. Para sumar Rosario alcanza con dejar
su GeoJSON en data/geo y agregar la entrada en CAPAS_ZONA: la corrida
siguiente de silver reasigna sola.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple, Optional

CAPAS_ZONA = {
    "ecobici-buenos-aires": {
        "archivo": "caba_barrios.geojson",
        "nivel": "barrio",
        "campo_zona": "nombre",
        "campo_padre": "comuna",
        "prefijo_padre": "Comuna ",
    },
}

# Estaciones en la costa o sobre una avenida limite caen apenas afuera del
# poligono. Hasta ~200 m (en grados) se asigna el poligono mas cercano.
TOLERANCIA_GRADOS = 0.002


class Capa(NamedTuple):
    arbol: Any                                  # shapely STRtree
    atributos: list[tuple[str, Optional[str]]]  # (zona, padre), mismo orden que el arbol
    nivel: str
    archivo: str


def cargar_capas(geo_dir: Path) -> dict[str, Capa]:
    """GeoJSON de CAPAS_ZONA -> {network_id: Capa}. La capa que falta se avisa y se saltea."""
    from shapely.geometry import shape  # lazy: solo silver lo necesita
    from shapely.strtree import STRtree

    capas = {}
    for red, cfg in CAPAS_ZONA.items():
        ruta = geo_dir / cfg["archivo"]
        if not ruta.exists():
            print(f"[zonas] {red}: falta {ruta}, se usa la ciudad como zona")
            continue
        geometrias, atributos = [], []
        for f in json.loads(ruta.read_text(encoding="utf-8"))["features"]:
            props = f["properties"]
            padre = props.get(cfg["campo_padre"]) if cfg.get("campo_padre") else None
            geometrias.append(shape(f["geometry"]))
            atributos.append((
                props[cfg["campo_zona"]],
                f"{cfg.get('prefijo_padre', '')}{padre}" if padre is not None else None,
            ))
        capas[red] = Capa(STRtree(geometrias), atributos, cfg["nivel"], cfg["archivo"])
    return capas


def _buscar(capa: Capa, lat: float, lon: float):
    """(zona, padre) del poligono que contiene el punto, o del mas cercano
    dentro de TOLERANCIA_GRADOS. None si no hay ninguno."""
    from shapely.geometry import Point

    punto = Point(lon, lat)  # GeoJSON: (longitud, latitud)
    for i in capa.arbol.query(punto, predicate="intersects"):
        return capa.atributos[int(i)]
    cercanos = capa.arbol.query_nearest(punto, max_distance=TOLERANCIA_GRADOS)
    if len(cercanos):
        return capa.atributos[int(cercanos[0])]
    return None


def zona_de(capas: dict[str, Capa], network_id: str, lat: float, lon: float,
            ciudad: Optional[str]) -> dict:
    """Zona de una estacion: {zona, zona_padre, zona_nivel, capa}.

    Sin capa para la red, o afuera de todos sus poligonos, cae a la ciudad
    (o al network_id si la red no tiene ciudad) con capa = 'fallback'.
    """
    capa = capas.get(network_id)
    encontrada = _buscar(capa, lat, lon) if capa else None
    if encontrada:
        zona, padre = encontrada
        return {"zona": zona, "zona_padre": padre, "zona_nivel": capa.nivel, "capa": capa.archivo}
    return {"zona": ciudad or network_id, "zona_padre": None,
            "zona_nivel": "ciudad", "capa": "fallback"}
