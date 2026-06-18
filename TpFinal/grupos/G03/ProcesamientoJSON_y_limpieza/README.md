Se desanidó el JSON de la API Open‑Meteo separando clima actual y pronóstico.
Se transformó a DataFrames utilizando Pandas, asegurando tipos de datos correctos mediante pd.to_numeric y pd.to_datetime.
Se eliminaron valores nulos y duplicados para garantizar consistencia en la capa silver.
