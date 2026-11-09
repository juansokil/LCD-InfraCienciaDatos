from datetime import date
import unittest
from unittest.mock import call, patch

import pandas as pd
from sqlalchemy.exc import SQLAlchemyError
from streamlit.testing.v1 import AppTest

from dashboard import app


CONSULTA_PRONOSTICO = "SELECT * FROM gold.v_ultimo_pronostico"
CONSULTA_COMPARACION = "SELECT * FROM gold.v_comparacion_ciudades"


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.pantalla = AppTest.from_string(
            "from dashboard.app import render_dashboard\nrender_dashboard()",
            default_timeout=15,
        )

    def test_consulta_solo_vistas_gold(self):
        with patch.object(app, "_leer_gold", return_value=pd.DataFrame()) as leer:
            self.pantalla.run()

        self.assertEqual(
            leer.call_args_list,
            [call(CONSULTA_PRONOSTICO), call(CONSULTA_COMPARACION)],
        )

    def test_gold_vacio_muestra_un_aviso(self):
        with patch.object(app, "_leer_gold", return_value=pd.DataFrame()):
            self.pantalla.run()

        self.assertFalse(self.pantalla.exception)
        self.assertIn("Todavía no hay pronósticos", self.pantalla.info[0].value)
        self.assertFalse(self.pantalla.dataframe)

    def test_error_de_conexion_muestra_un_aviso(self):
        with patch.object(app, "_leer_gold", side_effect=SQLAlchemyError("sin conexión")):
            self.pantalla.run()

        self.assertFalse(self.pantalla.exception)
        self.assertIn("No pudimos consultar Gold", self.pantalla.warning[0].value)

    def test_muestra_graficos_ranking_alertas_y_aplica_filtros(self):
        dia_1 = date(2026, 11, 9)
        dia_2 = date(2026, 11, 10)
        pronostico = pd.DataFrame(
            {
                "ciudad_id": [1, 2, 1, 2],
                "nombre": ["Buenos Aires", "Bariloche"] * 2,
                "fecha": [dia_1, dia_1, dia_2, dia_2],
                "fecha_id": [20261109, 20261109, 20261110, 20261110],
                "fecha_consulta_utc": pd.to_datetime(["2026-11-09T13:00:00Z"] * 4),
                "temp_max_c": [28.0, 16.0, 36.0, 18.0],
                "temp_min_c": [17.0, 5.0, 19.0, 6.0],
                "sensacion_termica_max_c": [28.0, 16.0, 37.0, 18.0],
                "precipitacion_mm": [0.0, 24.0, 3.0, 0.0],
                "viento_max_kmh": [15.0, 20.0, 15.0, 20.0],
            }
        )
        comparacion = pronostico.drop(
            columns=["fecha_id", "fecha_consulta_utc", "sensacion_termica_max_c"]
        ).assign(
            amplitud_termica_c=[11.0, 11.0, 17.0, 12.0],
            alerta_calor=[False, False, True, False],
            alerta_lluvia=[False, True, False, False],
        )
        vistas = {
            CONSULTA_PRONOSTICO: pronostico,
            CONSULTA_COMPARACION: comparacion,
        }

        with patch.object(app, "_leer_gold", side_effect=vistas.__getitem__):
            self.pantalla.run()
            self.assertFalse(self.pantalla.exception)
            self.assertEqual(len(self.pantalla.get("plotly_chart")), 2)
            self.assertTrue(any("09/11/2026 10:00" in c.value for c in self.pantalla.caption))

            alertas, ranking, tabla = (elemento.value for elemento in self.pantalla.dataframe)
            self.assertEqual(alertas["Ciudad"].tolist(), ["Bariloche", "Buenos Aires"])
            self.assertEqual(alertas["Calor"].tolist(), [False, True])
            self.assertEqual(alertas["Precipitación"].tolist(), [True, False])
            self.assertEqual(ranking["Ciudad"].tolist(), ["Buenos Aires", "Bariloche"])
            self.assertEqual(len(tabla), 4)

            self.pantalla.sidebar.multiselect[0].set_value(["Buenos Aires"])
            self.pantalla.sidebar.date_input[0].set_value((dia_2, dia_2))
            self.pantalla.run()
            self.assertFalse(self.pantalla.exception)

            alertas, ranking, tabla = (elemento.value for elemento in self.pantalla.dataframe)
            self.assertEqual(alertas["Calor"].tolist(), [True])
            self.assertEqual(ranking["Máxima (°C)"].tolist(), [36.0])
            self.assertEqual(tabla["Ciudad"].tolist(), ["Buenos Aires"])
            self.assertEqual(pd.to_datetime(tabla["Fecha"]).dt.date.tolist(), [dia_2])
