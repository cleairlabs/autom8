from autom8 import ToolResult


def weather_search_tool(location: str) -> ToolResult:
    """
    Return weather information for a given location.
    :param location: The location to search for.
    :return: The weather information.
    """
    weather = {"location": location,
               "temperature_celsius": 22,
               "condition": "Sunny",
               "forecast": "Clear skies all day."}
    return ToolResult(type="data", values=[weather], model_output=weather)
