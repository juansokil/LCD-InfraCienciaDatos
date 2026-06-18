import os
from datetime import datetime

from airflow.decorators import dag, task


DB_URI = (
    f"postgresql+psycopg2://"
    f"{os.getenv('SOURCE_DB_USER', 'admin')}:"
    f"{os.getenv('SOURCE_DB_PASS', 'admin')}@"
    f"{os.getenv('SOURCE_DB_HOST', 'data_warehouse')}:5432/"
    f"{os.getenv('SOURCE_DB_NAME', 'TpFinal')}"
)


@dag(
    dag_id="g08_openmeteo_gold",
    start_date=datetime(2026, 6, 17),
    schedule="20 * * * *",
    catchup=False,
    is_paused_upon_creation=False,
    tags=["g08", "gold", "openmeteo"],
)
def openmeteo_gold():
    @task
    def build_weather_daily_summary():
        import sqlalchemy

        engine = sqlalchemy.create_engine(DB_URI)

        with engine.begin() as conn:
            conn.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS gold;"))
            conn.execute(
                sqlalchemy.text(
                    """
                    CREATE TABLE IF NOT EXISTS gold.weather_daily_summary (
                        city TEXT NOT NULL,
                        forecast_date DATE NOT NULL,
                        avg_temperature DOUBLE PRECISION,
                        max_temperature DOUBLE PRECISION,
                        min_temperature DOUBLE PRECISION,
                        temperature_range DOUBLE PRECISION,
                        total_precipitation DOUBLE PRECISION,
                        rainy_hours INTEGER,
                        avg_wind_speed DOUBLE PRECISION,
                        max_wind_speed DOUBLE PRECISION,
                        hourly_records INTEGER,
                        weather_category TEXT,
                        outdoor_score INTEGER,
                        outdoor_recommendation TEXT,
                        updated_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (city, forecast_date)
                    );
                    """
                )
            )

            silver_exists = conn.execute(
                sqlalchemy.text("SELECT to_regclass('silver.weather_hourly')")
            ).scalar()
            if not silver_exists:
                print("silver.weather_hourly no existe todavia. Ejecutar Silver primero.")
                return

            result = conn.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO gold.weather_daily_summary (
                        city,
                        forecast_date,
                        avg_temperature,
                        max_temperature,
                        min_temperature,
                        temperature_range,
                        total_precipitation,
                        rainy_hours,
                        avg_wind_speed,
                        max_wind_speed,
                        hourly_records,
                        weather_category,
                        outdoor_score,
                        outdoor_recommendation,
                        updated_at
                    )
                    WITH daily AS (
                        SELECT
                            city,
                            (forecast_time AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS forecast_date,
                            ROUND(AVG(temperature_2m)::numeric, 2)::double precision AS avg_temperature,
                            MAX(temperature_2m) AS max_temperature,
                            MIN(temperature_2m) AS min_temperature,
                            ROUND((MAX(temperature_2m) - MIN(temperature_2m))::numeric, 2)::double precision AS temperature_range,
                            ROUND(SUM(COALESCE(precipitation, 0))::numeric, 2)::double precision AS total_precipitation,
                            COUNT(*) FILTER (WHERE COALESCE(precipitation, 0) > 0) AS rainy_hours,
                            ROUND(AVG(wind_speed_10m)::numeric, 2)::double precision AS avg_wind_speed,
                            ROUND(MAX(wind_speed_10m)::numeric, 2)::double precision AS max_wind_speed,
                            COUNT(*) AS hourly_records
                        FROM silver.weather_hourly
                        GROUP BY city, (forecast_time AT TIME ZONE 'America/Argentina/Buenos_Aires')::date
                    ),
                    scored AS (
                        SELECT
                            *,
                            CASE
                                WHEN total_precipitation > 5 OR rainy_hours >= 4 THEN 'lluvioso'
                                WHEN max_wind_speed >= 30 THEN 'ventoso'
                                WHEN avg_temperature < 10 THEN 'frio'
                                WHEN avg_temperature > 28 THEN 'caluroso'
                                ELSE 'agradable'
                            END AS weather_category,
                            GREATEST(
                                0,
                                LEAST(
                                    100,
                                    100
                                    - CASE WHEN total_precipitation > 5 THEN 35 ELSE 0 END
                                    - CASE WHEN rainy_hours >= 4 THEN 20 ELSE 0 END
                                    - CASE WHEN max_wind_speed >= 30 THEN 20 ELSE 0 END
                                    - CASE WHEN avg_temperature < 10 THEN 15 ELSE 0 END
                                    - CASE WHEN avg_temperature > 28 THEN 15 ELSE 0 END
                                )
                            )::int AS outdoor_score
                        FROM daily
                    )
                    SELECT
                        city,
                        forecast_date,
                        avg_temperature,
                        max_temperature,
                        min_temperature,
                        temperature_range,
                        total_precipitation,
                        rainy_hours,
                        avg_wind_speed,
                        max_wind_speed,
                        hourly_records,
                        weather_category,
                        outdoor_score,
                        CASE
                            WHEN weather_category = 'lluvioso' THEN 'Dia con lluvia: revisar horarios antes de salir'
                            WHEN outdoor_score >= 80 THEN 'Buen dia para actividades al aire libre'
                            WHEN outdoor_score >= 60 THEN 'Dia aceptable, revisar condiciones'
                            WHEN outdoor_score >= 40 THEN 'Precaucion por clima'
                            ELSE 'No recomendado para actividades al aire libre'
                        END AS outdoor_recommendation,
                        NOW() AS updated_at
                    FROM scored
                    ON CONFLICT (city, forecast_date)
                    DO UPDATE SET
                        avg_temperature = EXCLUDED.avg_temperature,
                        max_temperature = EXCLUDED.max_temperature,
                        min_temperature = EXCLUDED.min_temperature,
                        temperature_range = EXCLUDED.temperature_range,
                        total_precipitation = EXCLUDED.total_precipitation,
                        rainy_hours = EXCLUDED.rainy_hours,
                        avg_wind_speed = EXCLUDED.avg_wind_speed,
                        max_wind_speed = EXCLUDED.max_wind_speed,
                        hourly_records = EXCLUDED.hourly_records,
                        weather_category = EXCLUDED.weather_category,
                        outdoor_score = EXCLUDED.outdoor_score,
                        outdoor_recommendation = EXCLUDED.outdoor_recommendation,
                        updated_at = EXCLUDED.updated_at;
                    """
                )
            )

        print(
            "Gold Open-Meteo: "
            f"{result.rowcount} filas insertadas/actualizadas en "
            "gold.weather_daily_summary."
        )

    build_weather_daily_summary()


openmeteo_gold()
