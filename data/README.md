# Data folder

The dataset is **not** stored in this repository. It is about 2 GB (well over
GitHub's 100 MB file limit) and is owned by Monash University, so it is not
ours to redistribute. Git ignores everything in this folder except this file.

## How to get the data

1. Download the MMA3001 project dataset ("Monash Smart Infrastructure
   Occupancy and Environmental Data") from the unit's Moodle page.
2. Unzip the two CSV files into `data/raw/`:

```
data/
├── raw/
│   ├── 5EnvSensor_MayToDec2024_180kRows.csv          (~350 MB)
│   ├── 5occupancySensor_MayToDec2024_9MRows.csv      (~1.6 GB)
│   └── Sensor ID and Locations.xlsx
└── processed/      (created by the code; cleaned data saved as Parquet)
```

## Raw file contents (as provided)

| File | Columns |
|---|---|
| Environmental sensors | `id, sensorid, devicetype, jsondata, status, processing_errors, createdate, processdate` — the readings themselves (e.g. battery voltage, CO2 in ppm) are nested inside the `jsondata` column as JSON text with Unix timestamps. |
| Occupancy sensors | `id, deviceid, floorspaceid, occupancystatus, headcount, collecteddate, occupancystatuschangedate, previousoccupancystatus` |

Rules: files in `raw/` are never modified. Anything the code produces goes in
`processed/`.
