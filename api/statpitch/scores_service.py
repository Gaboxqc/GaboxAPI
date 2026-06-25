"""
Scores service — fetches completed match results from The Odds API.

Uses the /scores/ endpoint which returns live and recently completed matches.
Same API key as odds_service.py — no extra cost beyond the request count.

The Odds API free tier: 500 requests/month.
Result checker runs every 60 min only when unresolved matches exist.
Estimated usage: ~360 score checks + 30 syncs = ~390/month (within free tier).
"""

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import HTTPException, status

_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
_DEFAULT_SPORT = "soccer_fifa_world_cup"

# Re-use the same normalization map from odds_service
_TEAM_NAME_MAP: dict[str, str] = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Korea Republic":       "South Korea",
    "IR Iran":              "Iran",
    "USA":                  "United States",
    "Côte d'Ivoire":        "Ivory Coast",
}


def _normalize(name: str) -> str:
    return _TEAM_NAME_MAP.get(name, name)


@dataclass
class MatchScore:
    """Result of a completed match."""
    home_team: str
    away_team: str
    match_date: date
    completed: bool
    actual_result: Optional[str]  # "home_win" | "draw" | "away_win" | None if not completed


def _determine_result(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home_win"
    elif home_score < away_score:
        return "away_win"
    else:
        return "draw"


async def fetch_recent_scores(days_back: int = 2) -> list[MatchScore]:
    """
    Fetch scores for recently completed matches.

    days_back=2 returns matches from the last 2 days, which covers:
    - Today's matches (may still be in progress)
    - Yesterday's matches (fully completed)

    Raises HTTPException on API errors, returns empty list on no data.
    """
    api_key = os.getenv("ODDS_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ODDS_API_KEY is not configured.",
        )

    sport = os.getenv("ODDS_API_SPORT", _DEFAULT_SPORT)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{_ODDS_API_BASE}/sports/{sport}/scores/",
                params={
                    "apiKey":   api_key,
                    "daysFrom": days_back,
                },
            )
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="The Odds API scores endpoint timed out.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Scores API returned HTTP {exc.response.status_code}.")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach scores API: {exc}")

    results: list[MatchScore] = []
    today    = date.today()
    tomorrow = today + timedelta(days=1)

    for event in response.json():
        # Parse UTC date
        commence_time = datetime.fromisoformat(
            event["commence_time"].replace("Z", "+00:00")
        )
        match_date_utc = commence_time.astimezone(timezone.utc).date()

        # Only care about today's matches (same window logic as odds_service)
        if match_date_utc not in {today, tomorrow}:
            continue

        home_team = _normalize(event.get("home_team", ""))
        away_team = _normalize(event.get("away_team", ""))
        completed = event.get("completed", False)

        actual_result: Optional[str] = None
        if completed:
            scores = {
                _normalize(s["name"]): int(s["score"])
                for s in (event.get("scores") or [])
                if s.get("score") is not None
            }
            home_score = scores.get(home_team)
            away_score = scores.get(away_team)
            if home_score is not None and away_score is not None:
                actual_result = _determine_result(home_score, away_score)

        results.append(MatchScore(
            home_team=home_team,
            away_team=away_team,
            match_date=today,   # always store under today
            completed=completed,
            actual_result=actual_result,
        ))

    return results
