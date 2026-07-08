DOMAIN = "air352"
MANUFACTURER = "352"

APPID_352 = "8d5018f2bc0f11ea8e6388e9fe5ac5b6"
BASE_URL_352 = "https://app.352air.com"

ALI_APP_KEY = "27554844"
ALI_APP_SECRET = "b66d2c9767cd15a7c5a088341055d134"
ALI_DOMAIN = "api.link.aliyun.com"
ALI_OA_DOMAIN = "living-account.cn-shanghai.aliyuncs.com"

DEFAULT_SCAN_INTERVAL = 10

CONF_IOT_TOKEN = "iot_token"
CONF_IOT_REFRESH_TOKEN = "iot_refresh_token"
CONF_IOT_TOKEN_EXPIRE = "iot_token_expire"

DEVICE_TYPE_AIR = "AirPurifier"
DEVICE_TYPE_HUMIDIFIER = "Humidifier"
DEVICE_TYPE_PURIFIER = "WaterPurifier"

CATEGORY_KEY_ALIASES = {
    DEVICE_TYPE_AIR.lower(): DEVICE_TYPE_AIR,
    DEVICE_TYPE_HUMIDIFIER.lower(): DEVICE_TYPE_HUMIDIFIER,
    DEVICE_TYPE_PURIFIER.lower(): DEVICE_TYPE_PURIFIER,
}


def normalize_device_category(category_key: str | None) -> str:
    """Normalize API categoryKey values to the integration's canonical names."""
    if not category_key:
        return ""
    category = str(category_key)
    return CATEGORY_KEY_ALIASES.get(category.lower(), category)
