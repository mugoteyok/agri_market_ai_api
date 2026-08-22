from fastapi import APIRouter, HTTPException
import httpx


router = APIRouter()


# ============================================================
# LOCATION NORMALIZATION
#
# Cleans the farmer's saved region before sending it to the
# geocoding service.
#
# Examples:
#
# Jinja
# Jinja, Uganda
# Jinja City, Uganda
#
# are normalized before geocoding.
# ============================================================

def clean_location_name(location: str) -> str:

    location = location.strip()

    suffixes = [
        ", Uganda",
        ", uganda",
    ]

    for suffix in suffixes:

        if location.endswith(suffix):

            location = location[
                :-len(suffix)
            ].strip()

    return location


# ============================================================
# LOCATION GEOCODING
#
# Converts a farmer's region/town into coordinates dynamically.
#
# No hard-coded Uganda location list is required.
# ============================================================

async def geocode_location(
    location_name: str,
):

    url = (
        "https://geocoding-api.open-meteo.com/v1/search"
    )

    params = {

        "name": location_name,

        "count": 10,

        "language": "en",

        "format": "json",
    }

    try:

        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:

            response = await client.get(
                url,
                params=params,
            )

            response.raise_for_status()

            data = response.json()

    except httpx.HTTPError as e:

        raise HTTPException(
            status_code=502,
            detail=(
                "Location service is temporarily unavailable."
            ),
        ) from e

    results = data.get(
        "results",
        [],
    )

    if not results:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Could not find location "
                f"'{location_name}'."
            ),
        )

    # --------------------------------------------------------
    # Prefer Uganda when multiple places have the same name.
    # --------------------------------------------------------

    uganda_results = [

        result

        for result in results

        if result.get(
            "country_code",
            "",
        ).upper() == "UG"

    ]

    if uganda_results:

        location = uganda_results[0]

    else:

        location = results[0]

    return {

        "name": location.get(
            "name",
            location_name,
        ),

        "latitude": float(
            location["latitude"]
        ),

        "longitude": float(
            location["longitude"]
        ),

        "country": location.get(
            "country",
            "Uganda",
        ),

        "admin1": location.get(
            "admin1",
            "",
        ),

        "admin2": location.get(
            "admin2",
            "",
        ),

        "timezone": location.get(
            "timezone",
            "Africa/Kampala",
        ),
    }


# ============================================================
# WEATHER CODE DESCRIPTION
# ============================================================

def weather_description(
    code: int,
) -> str:

    descriptions = {

        0: "Clear sky",

        1: "Mainly clear",

        2: "Partly cloudy",

        3: "Overcast",

        45: "Fog",

        48: "Depositing rime fog",

        51: "Light drizzle",

        53: "Moderate drizzle",

        55: "Dense drizzle",

        56: "Light freezing drizzle",

        57: "Dense freezing drizzle",

        61: "Slight rain",

        63: "Moderate rain",

        65: "Heavy rain",

        66: "Light freezing rain",

        67: "Heavy freezing rain",

        71: "Slight snowfall",

        73: "Moderate snowfall",

        75: "Heavy snowfall",

        77: "Snow grains",

        80: "Slight rain showers",

        81: "Moderate rain showers",

        82: "Violent rain showers",

        85: "Slight snow showers",

        86: "Heavy snow showers",

        95: "Thunderstorm",

        96: "Thunderstorm with slight hail",

        99: "Thunderstorm with heavy hail",
    }

    return descriptions.get(
        code,
        "Variable weather conditions",
    )


# ============================================================
# FARM ACTION ENGINE
# ============================================================

def generate_farm_action(
    rain_probability: int,
    rainfall: float,
    wind_speed: float,
    weather_code: int,
):

    # --------------------------------------------------------
    # HEAVY RAIN / HIGH RAIN PROBABILITY
    # --------------------------------------------------------

    if (
        rain_probability >= 70
        or rainfall >= 10
    ):

        return {

            "english": (
                "Rain is likely today. "
                "Avoid spraying pesticides or foliar "
                "fertilizers close to the expected rainfall."
            ),

            "luganda": (
                "Enkuba esuubirwa leero. "
                "Weewale okufuuyira eddagala ly'ebirime "
                "oba ebigimusa ku makoola nga enkuba "
                "enaatera okutonnya."
            ),
        }

    # --------------------------------------------------------
    # STRONG WIND
    # --------------------------------------------------------

    if wind_speed >= 30:

        return {

            "english": (
                "Strong winds are expected. "
                "Postpone spraying and secure vulnerable crops."
            ),

            "luganda": (
                "Empewo ennyo esuubirwa. "
                "Yongeza okufuuyira era onyweze ebirime "
                "ebiyinza okukosebwa."
            ),
        }

    # --------------------------------------------------------
    # DRY CONDITIONS
    # --------------------------------------------------------

    if (
        rain_probability <= 20
        and rainfall < 1
    ):

        return {

            "english": (
                "Dry conditions are expected. "
                "Inspect your crops and monitor soil moisture."
            ),

            "luganda": (
                "Embeera enkalu esuubirwa. "
                "Kebera ebirime byo era londoola "
                "obunnyogovu bw'ettaka."
            ),
        }

    # --------------------------------------------------------
    # NORMAL CONDITIONS
    # --------------------------------------------------------

    return {

        "english": (
            "Conditions are suitable for routine farm work. "
            "Inspect your crops and plan activities according "
            "to the latest weather conditions."
        ),

        "luganda": (
            "Embeera esaanira emirimu gy'omu nnimiro "
            "egya bulijjo. "
            "Kebera ebirime byo era oteekateeke emirimu "
            "ng'otunuulira embeera y'obudde."
        ),
    }


# ============================================================
# PRECISION IRRIGATION ENGINE
#
# This is the CENTRAL agricultural decision engine.
#
# Inputs:
#
# - Rain probability
# - Expected rainfall
# - ET0
# - Temperature
# - Humidity
# - Tomorrow's rain probability
# - Tomorrow's rainfall
#
# IMPORTANT:
#
# Actual soil moisture is NOT currently available.
#
# Therefore:
#
# irrigation_recommended = WEATHER/ET0 DECISION
#
# It does NOT claim that the soil is definitely dry.
#
# Future:
#
# Soil sensor/API
#       ↓
# Actual soil moisture
#       ↓
# More precise irrigation decision
# ============================================================

def generate_precision_irrigation(
    rain_probability: int,
    rainfall: float,
    evapotranspiration: float,
    temperature: float,
    humidity: int,
    tomorrow_rain_probability: int,
    tomorrow_rainfall: float,
):

    # ========================================================
    # IRRIGATION SCORE
    #
    # 0 - 100
    #
    # Higher score = greater atmospheric irrigation pressure.
    #
    # This is a decision-support score.
    # It is NOT measured soil moisture.
    # ========================================================

    score = 0

    # --------------------------------------------------------
    # RAIN PROBABILITY
    # --------------------------------------------------------

    if rain_probability <= 20:

        score += 30

    elif rain_probability <= 40:

        score += 15

    elif rain_probability >= 70:

        score -= 30

    elif rain_probability >= 50:

        score -= 15

    # --------------------------------------------------------
    # EXPECTED RAINFALL
    # --------------------------------------------------------

    if rainfall < 1:

        score += 25

    elif rainfall < 3:

        score += 10

    elif rainfall >= 10:

        score -= 30

    elif rainfall >= 5:

        score -= 20

    # --------------------------------------------------------
    # EVAPOTRANSPIRATION
    #
    # ET0 represents atmospheric water demand.
    # Higher ET0 generally means greater water loss.
    # --------------------------------------------------------

    if evapotranspiration >= 6:

        score += 25

    elif evapotranspiration >= 4:

        score += 15

    elif evapotranspiration < 2:

        score -= 5

    # --------------------------------------------------------
    # TEMPERATURE
    # --------------------------------------------------------

    if temperature >= 32:

        score += 15

    elif temperature >= 28:

        score += 8

    elif temperature < 20:

        score -= 5

    # --------------------------------------------------------
    # HUMIDITY
    #
    # Lower humidity generally increases atmospheric
    # evaporative demand.
    # --------------------------------------------------------

    if humidity <= 40:

        score += 15

    elif humidity <= 55:

        score += 8

    elif humidity >= 80:

        score -= 8

    # --------------------------------------------------------
    # TOMORROW'S FORECAST
    #
    # If substantial rain is expected tomorrow, avoid
    # unnecessary irrigation today.
    # --------------------------------------------------------

    if (
        tomorrow_rain_probability >= 70
        or tomorrow_rainfall >= 10
    ):

        score -= 20

    elif (
        tomorrow_rain_probability <= 20
        and tomorrow_rainfall < 1
    ):

        score += 10

    # --------------------------------------------------------
    # LIMIT SCORE
    # --------------------------------------------------------

    score = max(
        0,
        min(
            100,
            score,
        ),
    )

    # ========================================================
    # FORECAST TREND
    # ========================================================

    if (
        tomorrow_rain_probability >= 70
        or tomorrow_rainfall >= 10
    ):

        forecast_trend = "rain_increasing"

    elif (
        tomorrow_rain_probability <= 25
        and tomorrow_rainfall < 1
    ):

        forecast_trend = "dry_continuing"

    else:

        forecast_trend = "stable"

    # ========================================================
    # DETERMINE WATER DEMAND
    # ========================================================

    if score >= 70:

        water_demand = "high"

    elif score >= 40:

        water_demand = "moderate"

    else:

        water_demand = "low"

    # ========================================================
    # DEFAULT IRRIGATION DECISION
    # ========================================================

    irrigation_recommended = False

    priority = "low"

    status = "not_needed"

    # ========================================================
    # RAIN OVERRIDE
    #
    # Rain takes priority over atmospheric demand.
    #
    # Example:
    #
    # ET0 = high
    # BUT
    # Rain probability = 80%
    #
    # We should not tell the farmer to irrigate.
    # ========================================================

    if (
        rain_probability >= 60
        or rainfall >= 5
    ):

        status = "postpone"

        irrigation_recommended = False

        priority = "low"

        water_demand = "low"

        english = (
            "Rainfall is expected. "
            "Irrigation is not recommended at this time. "
            "Monitor soil moisture and reassess after the rainfall."
        )

        luganda = (
            "Enkuba esuubirwa. "
            "Okufukirira tekukubirizibwa mu kiseera kino. "
            "Londoola obunnyogovu bw'ettaka era oddemu okukebera "
            "oluvannyuma lw'enkuba."
        )

        irrigation_reason = (
            "Expected rainfall reduces the need for irrigation."
        )

        irrigation_reason_luganda = (
            "Enkuba esuubirwa ekendeeza obwetaavu "
            "bw'okufukirira."
        )

    # ========================================================
    # HIGH WATER DEMAND
    # ========================================================

    elif score >= 70:

        status = "recommended"

        irrigation_recommended = True

        priority = "high"

        water_demand = "high"

        english = (
            "Irrigation recommended. "
            "Rain probability is low and atmospheric water "
            "demand is elevated. Check soil moisture before "
            "irrigating and apply only the amount needed."
        )

        luganda = (
            "Okufukirira kukubirizibwa. "
            "Obusobozi bw'enkuba buli wansi ate obwetaavu "
            "bw'amazzi mu bbanga buli waggulu. "
            "Kebera obunnyogovu bw'ettaka nga tonafukirira "
            "era kozesa amazzi agagwanira."
        )

        irrigation_reason = (
            "Low rainfall probability combined with elevated "
            "atmospheric water demand indicates higher irrigation pressure."
        )

        irrigation_reason_luganda = (
            "Obusobozi bw'enkuba obutono awamu n'obwetaavu "
            "bw'amazzi obw'amaanyi mu bbanga biraga nti "
            "obwetaavu bw'okufukirira bweyongedde."
        )

    # ========================================================
    # MODERATE WATER DEMAND
    # ========================================================

    elif score >= 40:

        status = "monitor"

        irrigation_recommended = False

        priority = "medium"

        water_demand = "moderate"

        english = (
            "Moderate irrigation demand is expected. "
            "Check soil moisture before irrigating and "
            "consider a light irrigation only if the soil "
            "is becoming dry."
        )

        luganda = (
            "Obwetaavu bw'okufukirira obw'ekigero busuubirwa. "
            "Kebera obunnyogovu bw'ettaka nga tonafukirira "
            "era lowooza ku kufukirira okutono singa ettaka "
            "litandika okukala."
        )

        irrigation_reason = (
            "Weather conditions indicate moderate atmospheric "
            "water demand. Soil moisture should determine whether "
            "irrigation is actually needed."
        )

        irrigation_reason_luganda = (
            "Embeera y'obudde eraga obwetaavu bw'amazzi "
            "obw'ekigero. Obunnyogovu bw'ettaka bwe busaanidde "
            "okusalawo oba okufukirira kwetaagisa."
        )

    # ========================================================
    # LOW WATER DEMAND
    # ========================================================

    else:

        status = "not_needed"

        irrigation_recommended = False

        priority = "low"

        water_demand = "low"

        english = (
            "Irrigation demand is currently low. "
            "Avoid unnecessary watering and continue monitoring "
            "soil moisture and rainfall."
        )

        luganda = (
            "Obwetaavu bw'okufukirira kati buli wansi. "
            "Weewale okufukirira okutali kwetaagisa era "
            "weeyongere okulondoola obunnyogovu bw'ettaka "
            "n'enkuba."
        )

        irrigation_reason = (
            "Current rainfall and atmospheric conditions indicate "
            "low irrigation pressure."
        )

        irrigation_reason_luganda = (
            "Enkuba n'embeera y'obudde kati biraga nti "
            "obwetaavu bw'okufukirira buli wansi."
        )

    # ========================================================
    # RETURN PRECISION IRRIGATION DECISION
    # ========================================================

    return {

        "english": english,

        "luganda": luganda,

        "status": status,

        "priority": priority,

        "water_demand": water_demand,

        "score": score,

        "forecast_trend": forecast_trend,

        # --------------------------------------------------------
        # BOOLEAN IRRIGATION RECOMMENDATION
        #
        # True only when the backend determines that irrigation
        # should be recommended.
        #
        # False when irrigation should be monitored, postponed,
        # or is not currently needed.
        # --------------------------------------------------------

        "irrigation_recommended":
            status == "recommended",

        "reason": irrigation_reason,

        "reason_luganda":
            irrigation_reason_luganda,
    }


# ============================================================
# CROP HEALTH ENGINE
# ============================================================

def generate_crop_health(
    humidity: int,
    rain_probability: int,
):

    # --------------------------------------------------------
    # HIGH HUMIDITY + HIGH RAIN
    # --------------------------------------------------------

    if (
        humidity >= 80
        and rain_probability >= 60
    ):

        return {

            "english": (
                "High humidity and rainfall may increase the risk "
                "of fungal crop diseases. Inspect leaves and stems "
                "for early symptoms."
            ),

            "luganda": (
                "Obunnyogovu obungi n'enkuba biyinza okwongera "
                "obulabe bw'endwadde z'ebirime eziva ku fungi. "
                "Kebera amakoola n'ebikolo okulaba "
                "obubonero obusooka."
            ),
        }

    # --------------------------------------------------------
    # HIGH HUMIDITY
    # --------------------------------------------------------

    if humidity >= 75:

        return {

            "english": (
                "Humidity is relatively high. Monitor crops "
                "closely for early signs of disease."
            ),

            "luganda": (
                "Obunnyogovu bw'omu bbanga buli waggulu. "
                "Londoola ebirime byo okulaba obubonero "
                "bw'endwadde nga bukyali."
            ),
        }

    # --------------------------------------------------------
    # NORMAL CROP HEALTH RISK
    # --------------------------------------------------------

    return {

        "english": (
            "Current conditions do not indicate a strong "
            "weather-related disease risk. Continue routine "
            "crop inspection."
        ),

        "luganda": (
            "Embeera y'obudde kati telaga bulabe bwa maanyi "
            "obw'endwadde z'ebirime. "
            "Weeyongere okukebera ebirime byo."
        ),
    }


# ============================================================
# TOMORROW PLANNING
# ============================================================

def generate_tomorrow_recommendation(
    tomorrow_rain_probability: int,
    tomorrow_rainfall: float,
):

    # --------------------------------------------------------
    # HIGH RAIN PROBABILITY
    # --------------------------------------------------------

    if tomorrow_rain_probability >= 70:

        return {

            "english": (
                "Rain is likely tomorrow. "
                "Plan field activities that can be completed "
                "before the rainfall."
            ),

            "luganda": (
                "Enkuba esuubirwa enkya. "
                "Teekateeka emirimu gy'omu nnimiro "
                "egisobola okukolebwa nga enkuba "
                "tenatonnya."
            ),
        }

    # --------------------------------------------------------
    # LOW RAIN PROBABILITY
    # --------------------------------------------------------

    if tomorrow_rain_probability <= 25:

        return {

            "english": (
                "Dry conditions are expected tomorrow. "
                "This may provide a useful window for field work "
                "and crop inspection."
            ),

            "luganda": (
                "Embeera enkalu esuubirwa enkya. "
                "Kino kiyinza okuwa omukisa omulungi okukola "
                "emirimu gy'omu nnimiro n'okukebera ebirime."
            ),
        }

    # --------------------------------------------------------
    # MODERATE
    # --------------------------------------------------------

    return {

        "english": (
            "Moderate weather conditions are expected tomorrow. "
            "Check the updated forecast before planning "
            "major activities."
        ),

        "luganda": (
            "Embeera y'obudde ey'ekigero esuubirwa enkya. "
            "Kebera obudde obupya nga tonateekateeka "
            "emirimu emikulu."
        ),
    }


# ============================================================
# FARM INTELLIGENCE ENDPOINT
# ============================================================

@router.get(
    "/farm-intelligence"
)
async def get_farm_intelligence(
    region: str,
):

    # ========================================================
    # VALIDATE REGION
    # ========================================================

    if not region or not region.strip():

        raise HTTPException(
            status_code=400,
            detail="Region is required.",
        )

    # ========================================================
    # NORMALIZE LOCATION
    # ========================================================

    location_name = clean_location_name(
        region
    )

    if not location_name:

        raise HTTPException(
            status_code=400,
            detail="Valid region is required.",
        )

    # ========================================================
    # DYNAMIC GEOCODING
    # ========================================================

    location = await geocode_location(
        location_name
    )

    latitude = location["latitude"]

    longitude = location["longitude"]

    # ========================================================
    # OPEN-METEO FORECAST
    #
    # CURRENT:
    #
    # - temperature
    # - humidity
    # - precipitation
    # - weather code
    # - wind
    #
    # DAILY:
    #
    # - precipitation probability
    # - rainfall
    # - reference evapotranspiration
    # ========================================================

    url = (
        "https://api.open-meteo.com/v1/forecast"
    )

    params = {

        "latitude": latitude,

        "longitude": longitude,

        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "precipitation,"
            "weather_code,"
            "wind_speed_10m"
        ),

        "daily": (
            "precipitation_probability_max,"
            "rain_sum,"
            "reference_evapotranspiration"
        ),

        "forecast_days": 2,

        "timezone": "Africa/Kampala",

        "temperature_unit": "celsius",

        "wind_speed_unit": "kmh",

        "precipitation_unit": "mm",
    }

    # ========================================================
    # CALL WEATHER SERVICE
    # ========================================================

    try:

        async with httpx.AsyncClient(
            timeout=15.0
        ) as client:

            response = await client.get(
                url,
                params=params,
            )

            response.raise_for_status()

            weather_data = response.json()

    except httpx.HTTPError as e:

        raise HTTPException(
            status_code=502,
            detail=(
                "Weather service is temporarily unavailable."
            ),
        ) from e

    # ========================================================
    # EXTRACT CURRENT WEATHER
    # ========================================================

    current = weather_data.get(
        "current",
        {},
    )

    daily = weather_data.get(
        "daily",
        {},
    )

    temperature = float(
        current.get(
            "temperature_2m",
            0,
        )
    )

    humidity = int(
        current.get(
            "relative_humidity_2m",
            0,
        )
    )

    wind_speed = float(
        current.get(
            "wind_speed_10m",
            0,
        )
    )

    weather_code = int(
        current.get(
            "weather_code",
            0,
        )
    )

    precipitation = float(
        current.get(
            "precipitation",
            0,
        )
    )

    # ========================================================
    # DAILY FORECAST
    # ========================================================

    rain_probabilities = daily.get(
        "precipitation_probability_max",
        [],
    )

    rain_sums = daily.get(
        "rain_sum",
        [],
    )

    evapotranspiration = daily.get(
        "reference_evapotranspiration",
        [],
    )

    # ========================================================
    # TODAY
    # ========================================================

    today_rain_probability = int(
        rain_probabilities[0]
        if len(rain_probabilities) > 0
        else 0
    )

    today_rainfall = float(
        rain_sums[0]
        if len(rain_sums) > 0
        else 0
    )

    today_et0 = float(
        evapotranspiration[0]
        if len(evapotranspiration) > 0
        else 0
    )

    # ========================================================
    # TOMORROW
    # ========================================================

    tomorrow_rain_probability = int(
        rain_probabilities[1]
        if len(rain_probabilities) > 1
        else 0
    )

    tomorrow_rainfall = float(
        rain_sums[1]
        if len(rain_sums) > 1
        else 0
    )

    tomorrow_et0 = float(
        evapotranspiration[1]
        if len(evapotranspiration) > 1
        else 0
    )

    # ========================================================
    # GENERATE FARM ACTION
    # ========================================================

    farm_action = generate_farm_action(

        rain_probability=
            today_rain_probability,

        rainfall=
            today_rainfall,

        wind_speed=
            wind_speed,

        weather_code=
            weather_code,
    )

    # ========================================================
    # GENERATE PRECISION IRRIGATION
    #
    # IMPORTANT:
    #
    # FastAPI makes the agricultural decision here.
    #
    # Flutter only displays the result.
    # ========================================================

    irrigation = generate_precision_irrigation(

        rain_probability=
            today_rain_probability,

        rainfall=
            today_rainfall,

        evapotranspiration=
            today_et0,

        temperature=
            temperature,

        humidity=
            humidity,

        tomorrow_rain_probability=
            tomorrow_rain_probability,

        tomorrow_rainfall=
            tomorrow_rainfall,
    )

    # ========================================================
    # CROP HEALTH
    # ========================================================

    crop_health = generate_crop_health(

        humidity=
            humidity,

        rain_probability=
            today_rain_probability,
    )

    # ========================================================
    # TOMORROW
    # ========================================================

    tomorrow = generate_tomorrow_recommendation(

        tomorrow_rain_probability=
            tomorrow_rain_probability,

        tomorrow_rainfall=
            tomorrow_rainfall,
    )

    # ========================================================
    # RETURN FARM INTELLIGENCE
    # ========================================================

    return {

        # ----------------------------------------------------
        # LOCATION
        # ----------------------------------------------------

        "location":
            location["name"],

        "region":
            location["admin1"],

        "district":
            location["admin2"],

        "country":
            location["country"],

        "latitude":
            latitude,

        "longitude":
            longitude,

        "timezone":
            location["timezone"],

        # ----------------------------------------------------
        # CURRENT WEATHER
        # ----------------------------------------------------

        "temperature":
            temperature,

        "humidity":
            humidity,

        "rain_probability":
            today_rain_probability,

        "rainfall":
            today_rainfall,

        "current_precipitation":
            precipitation,

        "wind_speed":
            wind_speed,

        "weather_code":
            weather_code,

        "weather_description":
            weather_description(
                weather_code
            ),

        # ----------------------------------------------------
        # EVAPOTRANSPIRATION
        # ----------------------------------------------------

        "evapotranspiration":
            today_et0,

        # ----------------------------------------------------
        # FARM ACTION
        # ----------------------------------------------------

        "farm_action":
            farm_action["english"],

        "farm_action_luganda":
            farm_action["luganda"],

        # ----------------------------------------------------
        # PRECISION IRRIGATION
        # ----------------------------------------------------

        "irrigation":
            irrigation["english"],

        "irrigation_luganda":
            irrigation["luganda"],

        # ----------------------------------------------------
        # IRRIGATION STATUS
        #
        # Possible values:
        #
        # recommended
        # monitor
        # postpone
        # not_needed
        # ----------------------------------------------------

        "irrigation_status":
            irrigation["status"],

        # ----------------------------------------------------
        # IRRIGATION PRIORITY
        #
        # Possible values:
        #
        # high
        # medium
        # low
        # ----------------------------------------------------

        "irrigation_priority":
            irrigation["priority"],

        # ----------------------------------------------------
        # BOOLEAN IRRIGATION RECOMMENDATION
        #
        # This is now generated by the backend.
        #
        # True:
        #     status == "recommended"
        #
        # False:
        #     monitor
        #     postpone
        #     not_needed
        # ----------------------------------------------------

        "irrigation_recommended":
            irrigation["irrigation_recommended"],

        # ----------------------------------------------------
        # ATMOSPHERIC WATER DEMAND
        #
        # Possible values:
        #
        # high
        # moderate
        # low
        # ----------------------------------------------------

        "water_demand":
            irrigation["water_demand"],

        # ----------------------------------------------------
        # IRRIGATION SCORE
        #
        # Decision-support score from 0 to 100.
        # ----------------------------------------------------

        "irrigation_score":
            irrigation["score"],

        # ----------------------------------------------------
        # IRRIGATION REASON
        # ----------------------------------------------------

        "irrigation_reason":
            irrigation["reason"],

        "irrigation_reason_luganda":
            irrigation["reason_luganda"],

        # ----------------------------------------------------
        # FORECAST TREND
        #
        # Possible values:
        #
        # rain_increasing
        # dry_continuing
        # stable
        # ----------------------------------------------------

        "forecast_trend":
            irrigation["forecast_trend"],

        # ----------------------------------------------------
        # SOIL MOISTURE
        #
        # Not available yet.
        #
        # Do NOT estimate and present this as measured soil
        # moisture.
        # ----------------------------------------------------

        "soil_moisture":
            None,

        # ----------------------------------------------------
        # CROP HEALTH
        # ----------------------------------------------------

        "crop_health":
            crop_health["english"],

        "crop_health_luganda":
            crop_health["luganda"],

        # ----------------------------------------------------
        # TOMORROW
        # ----------------------------------------------------

        "tomorrow":
            tomorrow["english"],

        "tomorrow_luganda":
            tomorrow["luganda"],

        # ----------------------------------------------------
        # FORECAST DETAILS
        # ----------------------------------------------------

        "forecast": {

            "tomorrow_rain_probability":
                tomorrow_rain_probability,

            "tomorrow_rainfall":
                tomorrow_rainfall,

            "tomorrow_evapotranspiration":
                tomorrow_et0,
        },
    }
