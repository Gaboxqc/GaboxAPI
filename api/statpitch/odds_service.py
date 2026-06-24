import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException, status

_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
_DEFAULT_SPORT = "soccer_fifa_world_cup"
_DEFAULT_REGION = "eu"

_TEAM_NAME_MAP: dict[str, str] = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "USA": "United States",
    "Côte d'Ivoire": "Ivory Coast",
}


def _normalize_team_name(name: str) -> str:
    """Translate Odds API team names to the names the ML model understands."""
    return _TEAM_NAME_MAP.get(name, name)


@dataclass
class MatchOdds:
    """Parsed, bookmaker-averaged odds for a single match."""

    home_team: str
    away_team: str
    match_date: date
    odds_home: float
    odds_draw: float
    odds_away: float
    home_flag_url: Optional[str] = None
    away_flag_url: Optional[str] = None


def _team_to_flag_url(team_name: str) -> str:
    """
    Best-effort flag URL using flagcdn.com.
    Maps common national team names to ISO 3166-1 alpha-2 codes.
    Extend this dict as needed for your competition.
    """
    FLAG_MAP: dict[str, str] = {
        "argentina": "ar",
        "australia": "au",
        "belgium": "be",
        "brazil": "br",
        "cameroon": "cm",
        "canada": "ca",
        "chile": "cl",
        "colombia": "co",
        "costa rica": "cr",
        "croatia": "hr",
        "czech republic": "cz",
        "denmark": "dk",
        "ecuador": "ec",
        "egypt": "eg",
        "england": "gb-eng",
        "france": "fr",
        "germany": "de",
        "ghana": "gh",
        "iran": "ir",
        "italy": "it",
        "ivory coast": "ci",
        "japan": "jp",
        "south korea": "kr",
        "korea republic": "kr",
        "mexico": "mx",
        "morocco": "ma",
        "netherlands": "nl",
        "new zealand": "nz",
        "nigeria": "ng",
        "norway": "no",
        "panama": "pa",
        "paraguay": "py",
        "peru": "pe",
        "poland": "pl",
        "portugal": "pt",
        "qatar": "qa",
        "romania": "ro",
        "russia": "ru",
        "saudi arabia": "sa",
        "senegal": "sn",
        "serbia": "rs",
        "spain": "es",
        "sweden": "se",
        "switzerland": "ch",
        "tunisia": "tn",
        "ukraine": "ua",
        "united states": "us",
        "usa": "us",
        "uruguay": "uy",
        "venezuela": "ve",
        "wales": "gb-wls",
        "scotland": "gb-sct",
        "austria": "at",
        "hungary": "hu",
        "slovakia": "sk",
        "slovenia": "si",
        "turkey": "tr",
        "greece": "gr",
        "albania": "al",
        "georgia": "ge",
    }
    code = FLAG_MAP.get(team_name.lower())
    if not code:
        return ""
    return f"https://flagcdn.com/{code}.svg"


def _average_odds(
    bookmakers: list[dict], home_team: str, away_team: str
) -> tuple[float, float, float]:
    """
    Average h2h decimal odds across all bookmakers for robustness.
    Returns (odds_home, odds_draw, odds_away).
    """
    home_prices, draw_prices, away_prices = [], [], []

    preferred = os.getenv("ODDS_API_BOOKMAKERS", "")
    preferred_keys = {k.strip() for k in preferred.split(",") if k.strip()}

    for bm in bookmakers:
        if preferred_keys and bm.get("key") not in preferred_keys:
            continue
        for market in bm.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                name = _normalize_team_name(outcome.get("name", "")).lower()
                price = outcome.get("price", 0.0)
                if name == home_team.lower():
                    home_prices.append(price)
                elif name == away_team.lower():
                    away_prices.append(price)
                elif name == "draw":
                    draw_prices.append(price)

    if not home_prices or not away_prices or not draw_prices:
        raise ValueError(
            f"Could not extract odds for {home_team} vs {away_team}. "
            "Check team name mapping or bookmaker availability."
        )

    return (
        round(sum(home_prices) / len(home_prices), 3),
        round(sum(draw_prices) / len(draw_prices), 3),
        round(sum(away_prices) / len(away_prices), 3),
    )


async def fetch_todays_odds() -> list[MatchOdds]:
    api_key = os.getenv("ODDS_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ODDS_API_KEY is not configured on the server.",
        )

    sport = os.getenv("ODDS_API_SPORT", _DEFAULT_SPORT)
    region = os.getenv("ODDS_API_REGION", _DEFAULT_REGION)

    target_tz = ZoneInfo("America/Managua")
    today_local = datetime.now(target_tz).date()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            events_resp = await client.get(
                f"{_ODDS_API_BASE}/sports/{sport}/events/",
                params={"apiKey": api_key},
            )
            events_resp.raise_for_status()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="The Odds API timed out."
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"The Odds API returned HTTP {exc.response.status_code}.",
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not reach The Odds API: {exc}",
            )

        try:
            odds_resp = await client.get(
                f"{_ODDS_API_BASE}/sports/{sport}/odds/",
                params={
                    "apiKey": api_key,
                    "regions": region,
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
            )
            odds_resp.raise_for_status()
        except Exception:
            odds_resp = None

    odds_by_id: dict[str, dict] = {}

    odds_by_id: dict[str, dict] = {}
    if odds_resp:
        for event in odds_resp.json():
            odds_by_id[event["id"]] = event

    results: list[MatchOdds] = []

    for event in events_resp.json():

        commence_time = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))

        match_time_local = commence_time.astimezone(target_tz)
        match_date_local = match_time_local.date()

        if match_date_local != today_local:
            continue

        home_team = _normalize_team_name(event["home_team"])
        away_team = _normalize_team_name(event["away_team"])

        odds_home = odds_draw = odds_away = None
        if event["id"] in odds_by_id:
            try:
                odds_home, odds_draw, odds_away = _average_odds(
                    odds_by_id[event["id"]].get("bookmakers", []),
                    home_team,
                    away_team,
                )
            except ValueError:
                pass

        results.append(
            MatchOdds(
                home_team=home_team,
                away_team=away_team,
                match_date=today_local,
                odds_home=odds_home,
                odds_draw=odds_draw,
                odds_away=odds_away,
                home_flag_url=_team_to_flag_url(home_team),
                away_flag_url=_team_to_flag_url(away_team),
            )
        )

    return results
