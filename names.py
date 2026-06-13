"""Team name normalization. The historical dataset's names are canonical."""

ALIASES = {
    "USA": "United States",
    "United States of America": "United States",
    "Korea Republic": "South Korea",
    "Korea, South": "South Korea",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Türkiye": "Turkey",
    "Turkiye": "Turkey",
    "Czechia": "Czech Republic",
    "Curacao": "Curaçao",
    "IR Iran": "Iran",
    "Iran, Islamic Republic of": "Iran",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia": "Bosnia and Herzegovina",
    "Congo DR": "DR Congo",
    "Congo, Democratic Republic of the": "DR Congo",
    "Democratic Republic of the Congo": "DR Congo",
    "Korea DPR": "North Korea",
    "China PR": "China",
    "Cabo Verde": "Cape Verde",
}


def canon(name):
    """Return the canonical dataset form of a team name."""
    if name is None:
        return None
    n = name.replace(" ", " ").strip()
    return ALIASES.get(n, n)
