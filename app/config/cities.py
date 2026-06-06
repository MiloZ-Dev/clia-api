"""Catalog of cities polled by the weather collector.

The list is grouped by region purely for readability; consumers should treat it
as a flat sequence. It covers major population centers plus a handful of
climate-extreme locations to give downstream models a wide range of conditions.
"""

CITIES: list[str] = [
    # North America
    "New York", "Los Angeles", "Chicago", "Miami", "Houston",
    "Toronto", "Vancouver", "Montreal", "Mexico City", "Guadalajara", "San Diego",

    # Central America & Caribbean
    "Panama City", "San Jose", "Havana", "Kingston", "Santo Domingo",

    # South America
    "Buenos Aires", "Santiago", "Bogota", "Lima", "Quito",
    "Rio de Janeiro", "Sao Paulo", "Montevideo", "La Paz", "Asuncion", "Barranquilla",
    "Valledupar", "Viña del Mar", "Antofagasta", "Cali", "Candelaria",
    "Coari", "Cartagena", "Palmira", "Medellin", "Santa Marta",

    # Europe
    "London", "Paris", "Berlin", "Madrid", "Rome", "Barcelona", "Valencia",
    "Amsterdam", "Brussels", "Vienna", "Oslo", "Stockholm",
    "Copenhagen", "Dublin", "Lisbon", "Warsaw", "Athens",

    # Africa
    "Cairo", "Johannesburg", "Lagos", "Nairobi", "Casablanca",
    "Cape Town", "Accra", "Addis Ababa", "Dakar", "Luanda",

    # Asia
    "Tokyo", "Beijing", "Shanghai", "Seoul", "Bangkok",
    "Jakarta", "Manila", "Kuala Lumpur", "New Delhi", "Mumbai",
    "Dubai", "Tehran", "Istanbul", "Baghdad", "Riyadh", "Murmansk", "Baku",

    # Oceania
    "Sydney", "Melbourne", "Auckland", "Wellington", "Suva", "Darwin", "Hobart",

    # Extreme-climate locations
    "Yakutsk", "Ushuaia", "Nuuk", "Reykjavik",
    "Timbuktu", "Dallol", "Oymyakon", "El Azizia", "Ulan Bator",
]

# Convenience aliases.
ALL_CITIES: list[str] = CITIES
TOTAL_CITIES: int = len(CITIES)
