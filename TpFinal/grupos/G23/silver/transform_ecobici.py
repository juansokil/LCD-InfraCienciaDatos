import requests
import pandas as pd

url = "https://api.citybik.es/v2/networks/ecobici-buenos-aires"

data = requests.get(url).json()

df = pd.DataFrame(data["network"]["stations"])

df = df.rename(
    columns={
        "id": "station_id",
        "name": "station_name",
        "timestamp": "station_timestamp"
    }
)

df["uid"] = df["extra"].apply(lambda x: x.get("uid"))
df["renting"] = df["extra"].apply(lambda x: x.get("renting"))
df["returning"] = df["extra"].apply(lambda x: x.get("returning"))
df["last_updated"] = df["extra"].apply(lambda x: x.get("last_updated"))
df["address"] = df["extra"].apply(lambda x: x.get("address"))
df["slots"] = df["extra"].apply(lambda x: x.get("slots"))
df["normal_bikes"] = df["extra"].apply(lambda x: x.get("normal_bikes"))
df["virtual"] = df["extra"].apply(lambda x: x.get("virtual"))

print(
    df[
        [
            "station_id",
            "station_name",
            "free_bikes",
            "empty_slots",
            "slots",
            "address"
        ]
    ].head()
)