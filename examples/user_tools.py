def weather_search_tool(location: str) -> dict:
    """
    Return weather information for a given location.
    :param location: The location to search for.
    :return: The weather information.
    """
    return {
        "location": location,
        "temperature_celsius": 22,
        "condition": "Sunny",
        "forecast": "Clear skies all day."
    }
