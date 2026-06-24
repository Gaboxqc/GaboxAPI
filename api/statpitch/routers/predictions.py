import asyncio
import os
from datetime import date, timedelta
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from api.database import SessionDep
from api.security import validate_api_key
from api.statpitch.models import (
    DailyStatsRead,
    MatchPrediction,
    MatchPredictionBatchCreate,
    MatchPredictionCreate,
    MatchPredictionRead,
    MatchResultUpdate,
    MLPredictionResponse,
    SyncResultRead,
)
from api.statpitch.odds_service import MatchOdds, fetch_todays_odds

router = APIRouter()

_ML_TIMEOUT = 90.0
HIGH_CONFIDENCE_THRESHOLD = 0.70


# ==============================================================================
# HELPERS
# ==============================================================================

def _get_ml_url() -> str:
    url = os.getenv("STATPITCH_ML_URL", "").rstrip("/")
    if not url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="STATPITCH_ML_URL is not configured on the server.",
        )
    return url


def _predicted_outcome(p: MatchPrediction) -> str:
    probs = {
        "home_win": p.home_win_prob,
        "draw": p.draw_prob,
        "away_win": p.away_win_prob,
    }
    return max(probs, key=probs.get)


def _compute_ev(prediction: MatchPrediction) -> None:
    """
    Mutates prediction in-place with Expected Value for each outcome.

    EV = (model_probability × decimal_odds) - 1
    EV > 0  → the casino underestimates this outcome — value bet
    EV < 0  → casino overcharges — skip

    Example:
        Model says home wins with 74% probability.
        Casino offers 1.90 odds.
        EV = (0.74 × 1.90) - 1 = +0.406 → 40.6% edge ✅

        Model says away wins with 12% probability.
        Casino offers 5.50 odds.
        EV = (0.12 × 5.50) - 1 = -0.34 → -34% edge ❌
    """
    if not all([prediction.odds_home, prediction.odds_draw, prediction.odds_away]):
        prediction.ev_home = None
        prediction.ev_draw = None
        prediction.ev_away = None
        prediction.best_bet = None
        return

    prediction.ev_home  = round((prediction.home_win_prob * prediction.odds_home) - 1, 4)
    prediction.ev_draw  = round((prediction.draw_prob     * prediction.odds_draw)  - 1, 4)
    prediction.ev_away  = round((prediction.away_win_prob * prediction.odds_away)  - 1, 4)

    ev_map = {
        "home_win": prediction.ev_home,
        "draw":     prediction.ev_draw,
        "away_win": prediction.ev_away,
    }
    best = max(ev_map, key=ev_map.get)
    prediction.best_bet = best if ev_map[best] > 0 else None


def _ml_to_db(
    ml: MLPredictionResponse,
    target_date: date,
    is_neutral: bool,
    odds_home: Optional[float],
    odds_draw: Optional[float],
    odds_away: Optional[float],
    home_flag_url: Optional[str],
    away_flag_url: Optional[str],
) -> MatchPrediction:
    prediction = MatchPrediction(
        match_date=target_date,
        home_team=ml.home_team,
        away_team=ml.away_team,
        is_neutral=is_neutral,
        home_flag_url=home_flag_url,
        away_flag_url=away_flag_url,
        model_version=ml.model_version,
        home_xg=ml.expected_goals.home,
        away_xg=ml.expected_goals.away,
        home_elo=ml.team_info.home_elo,
        away_elo=ml.team_info.away_elo,
        elo_diff=ml.team_info.elo_diff,
        h2h_games=ml.team_info.h2h_games,
        h2h_home_wins=ml.team_info.h2h_home_wins,
        home_win_prob=ml.match_result.home_win,
        draw_prob=ml.match_result.draw,
        away_win_prob=ml.match_result.away_win,
        over_1_5=ml.over_under.over_1_5,
        over_2_5=ml.over_under.over_2_5,
        over_3_5=ml.over_under.over_3_5,
        btts_yes=ml.btts.yes,
        btts_no=ml.btts.no,
        odds_home=odds_home,
        odds_draw=odds_draw,
        odds_away=odds_away,
    )
    _compute_ev(prediction)
    return prediction


async def _fetch_ml_one(
    client: httpx.AsyncClient,
    home_team: str,
    away_team: str,
    is_neutral: bool = True,
) -> MLPredictionResponse:
    try:
        response = await client.get(
            f"{_get_ml_url()}/{home_team}/{away_team}",
            params={"is_neutral": is_neutral},
        )
        response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                f"ML model timed out on {home_team} vs {away_team}. "
                "It may still be warming up — wait 60 s and retry."
            ),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ML model returned HTTP {exc.response.status_code} for {home_team} vs {away_team}.",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach ML model: {exc}",
        )
    return MLPredictionResponse.model_validate(response.json())


def _get_existing(
    db: SessionDep,
    target_date: date,
    home_team: str,
    away_team: str,
) -> Optional[MatchPrediction]:
    return db.exec(
        select(MatchPrediction).where(
            MatchPrediction.match_date == target_date,
            MatchPrediction.home_team == home_team,
            MatchPrediction.away_team == away_team,
        )
    ).first()


def _upsert(
    db: SessionDep,
    prediction: MatchPrediction,
    existing: Optional[MatchPrediction],
) -> MatchPrediction:
    if existing:
        for field, value in prediction.model_dump(exclude={"id"}).items():
            setattr(existing, field, value)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return prediction


# ==============================================================================
# WRITE ENDPOINTS  (API-key protected)
# ==============================================================================

@router.post(
    "/predictions/sync",
    response_model=SyncResultRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_api_key)],
    summary="Full daily sync — fetch today's matches, odds, and ML predictions automatically",
    description=(
        "One call to rule them all. Fetches today's World Cup matches and casino odds "
        "from The Odds API, then calls the ML model concurrently for each match, "
        "computes Expected Value for every outcome, and stores everything. "
        "Already-cached matches are skipped unless `force=true`."
    ),
)
async def sync_predictions(
    db: SessionDep,
    force: bool = Query(False, description="Re-fetch and overwrite already-cached matches."),
    is_neutral: bool = Query(True, description="Whether the venue is neutral (always true for World Cup)."),
):
    today = date.today()

    # Step 1 — fetch today's matches + odds from The Odds API
    todays_odds: list[MatchOdds] = await fetch_todays_odds()

    if not todays_odds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The Odds API returned no matches for today. "
                   "The competition may be on a rest day, or the sport key is wrong.",
        )

    # Step 2 — separate already-cached from those needing ML calls
    to_fetch: list[tuple[MatchOdds, Optional[MatchPrediction]]] = []
    skipped: list[MatchPrediction] = []

    for odds in todays_odds:
        existing = _get_existing(db, today, odds.home_team, odds.away_team)
        if existing and not force:
            skipped.append(existing)
        else:
            to_fetch.append((odds, existing))

    synced: list[MatchPrediction] = []

    if to_fetch:
        # Step 3 — call ML model concurrently for all pending matches
        async with httpx.AsyncClient(timeout=_ML_TIMEOUT) as client:
            ml_responses = await asyncio.gather(
                *[
                    _fetch_ml_one(client, odds.home_team, odds.away_team, is_neutral)
                    for odds, _ in to_fetch
                ]
            )

        # Step 4 — compute EV and persist
        for (odds, existing), ml_data in zip(to_fetch, ml_responses):
            prediction = _ml_to_db(
                ml=ml_data,
                target_date=today,
                is_neutral=is_neutral,
                odds_home=odds.odds_home,
                odds_draw=odds.odds_draw,
                odds_away=odds.odds_away,
                home_flag_url=odds.home_flag_url,
                away_flag_url=odds.away_flag_url,
            )
            synced.append(_upsert(db, prediction, existing))

    return SyncResultRead(
        synced=len(synced),
        skipped=len(skipped),
        date=today,
        matches=synced + skipped,
    )


@router.post(
    "/predictions",
    response_model=MatchPredictionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_api_key)],
    summary="Manually fetch and cache a single match prediction",
    description="Use this only to override or add a match not in The Odds API. For daily use, prefer /sync.",
)
async def create_prediction(
    payload: MatchPredictionCreate,
    db: SessionDep,
    force: bool = Query(False, description="Overwrite if already cached."),
):
    target_date = payload.match_date or date.today()
    existing = _get_existing(db, target_date, payload.home_team, payload.away_team)

    if existing and not force:
        return existing

    async with httpx.AsyncClient(timeout=_ML_TIMEOUT) as client:
        ml_data = await _fetch_ml_one(client, payload.home_team, payload.away_team, payload.is_neutral)

    return _upsert(
        db,
        _ml_to_db(
            ml=ml_data,
            target_date=target_date,
            is_neutral=payload.is_neutral,
            odds_home=payload.odds_home,
            odds_draw=payload.odds_draw,
            odds_away=payload.odds_away,
            home_flag_url=payload.home_flag_url,
            away_flag_url=payload.away_flag_url,
        ),
        existing,
    )


@router.post(
    "/predictions/batch",
    response_model=List[MatchPredictionRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_api_key)],
    summary="Manually batch-fetch predictions",
    description="Use this only to override multiple matches. For daily use, prefer /sync.",
)
async def create_predictions_batch(
    payload: MatchPredictionBatchCreate,
    db: SessionDep,
    force: bool = Query(False, description="Overwrite predictions that already exist."),
):
    if not payload.matches:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="matches list cannot be empty.",
        )

    fallback_date = payload.match_date or date.today()
    to_fetch: list[tuple[MatchPredictionCreate, date, Optional[MatchPrediction]]] = []
    already_cached: list[MatchPrediction] = []

    for match in payload.matches:
        target_date = match.match_date or fallback_date
        existing = _get_existing(db, target_date, match.home_team, match.away_team)
        if existing and not force:
            already_cached.append(existing)
        else:
            to_fetch.append((match, target_date, existing))

    results: list[MatchPrediction] = list(already_cached)

    if to_fetch:
        async with httpx.AsyncClient(timeout=_ML_TIMEOUT) as client:
            ml_responses = await asyncio.gather(
                *[
                    _fetch_ml_one(client, m.home_team, m.away_team, m.is_neutral)
                    for m, _, _ in to_fetch
                ]
            )

        for (match, target_date, existing), ml_data in zip(to_fetch, ml_responses):
            prediction = _upsert(
                db,
                _ml_to_db(
                    ml=ml_data,
                    target_date=target_date,
                    is_neutral=match.is_neutral,
                    odds_home=match.odds_home,
                    odds_draw=match.odds_draw,
                    odds_away=match.odds_away,
                    home_flag_url=match.home_flag_url,
                    away_flag_url=match.away_flag_url,
                ),
                existing,
            )
            results.append(prediction)

    order = {(m.home_team, m.away_team): i for i, m in enumerate(payload.matches)}
    results.sort(key=lambda p: order.get((p.home_team, p.away_team), 999))
    return results


@router.patch(
    "/predictions/{prediction_id}/result",
    response_model=MatchPredictionRead,
    dependencies=[Depends(validate_api_key)],
    summary="Record the actual result after a match ends",
    description="actual_result must be 'home_win', 'draw', or 'away_win'. Powers 30d accuracy and ROI.",
)
async def record_match_result(
    prediction_id: int,
    payload: MatchResultUpdate,
    db: SessionDep,
):
    prediction = db.get(MatchPrediction, prediction_id)
    if not prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prediction with id {prediction_id} not found",
        )
    prediction.actual_result = payload.actual_result
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return prediction


@router.delete(
    "/predictions/{prediction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(validate_api_key)],
)
async def delete_prediction(prediction_id: int, db: SessionDep):
    prediction = db.get(MatchPrediction, prediction_id)
    if not prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prediction with id {prediction_id} not found",
        )
    db.delete(prediction)
    db.commit()
    return None


# ==============================================================================
# READ ENDPOINTS  (public)
# ==============================================================================

@router.get(
    "/predictions/stats",
    response_model=DailyStatsRead,
    summary="Stats bar — predictions today, high confidence, value bets, 30d accuracy, 30d ROI",
)
async def get_stats(db: SessionDep):
    today = date.today()
    cutoff = today - timedelta(days=30)

    today_predictions = db.exec(
        select(MatchPrediction).where(MatchPrediction.match_date == today)
    ).all()

    predictions_today = len(today_predictions)

    high_confidence_today = sum(
        1 for p in today_predictions
        if max(p.home_win_prob, p.away_win_prob) >= HIGH_CONFIDENCE_THRESHOLD
    )

    value_bets_today = sum(
        1 for p in today_predictions if p.best_bet is not None
    )

    # Last 30 days — only settled matches
    settled = db.exec(
        select(MatchPrediction).where(
            MatchPrediction.match_date >= cutoff,
            MatchPrediction.match_date < today,
            MatchPrediction.actual_result.is_not(None),
        )
    ).all()

    settled_count = len(settled)

    accuracy_30d: Optional[float] = None
    if settled_count > 0:
        correct = sum(1 for p in settled if _predicted_outcome(p) == p.actual_result)
        accuracy_30d = round((correct / settled_count) * 100, 1)

    # ROI: flat-stake on the model's best_bet pick for each settled match with odds
    roi_30d: Optional[float] = None
    odds_map = {"home_win": "odds_home", "draw": "odds_draw", "away_win": "odds_away"}
    settled_with_odds = [
        p for p in settled
        if p.best_bet and getattr(p, odds_map.get(p.best_bet, ""), None) is not None
    ]
    if settled_with_odds:
        total_staked = len(settled_with_odds)
        total_returns = sum(
            getattr(p, odds_map[p.best_bet])
            for p in settled_with_odds
            if p.actual_result == p.best_bet
        )
        roi_30d = round(((total_returns - total_staked) / total_staked) * 100, 1)

    return DailyStatsRead(
        predictions_today=predictions_today,
        high_confidence_today=high_confidence_today,
        high_confidence_threshold=HIGH_CONFIDENCE_THRESHOLD,
        value_bets_today=value_bets_today,
        accuracy_30d=accuracy_30d,
        roi_30d=roi_30d,
        settled_matches_30d=settled_count,
    )


@router.get(
    "/predictions/today",
    response_model=List[MatchPredictionRead],
    summary="Get all of today's predictions, excluding the best pick",
)
async def get_today_predictions(db: SessionDep):
    predictions = db.exec(
        select(MatchPrediction)
        .where(MatchPrediction.match_date == date.today())
        .order_by(MatchPrediction.id)
    ).all()

    if not predictions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No predictions available for today yet.",
        )

    best_id = max(predictions, key=lambda p: max(p.home_win_prob, p.away_win_prob)).id
    return [p for p in predictions if p.id != best_id]


@router.get(
    "/predictions/today/best",
    response_model=MatchPredictionRead,
    summary="Get today's match with the highest win probability",
)
async def get_best_prediction_today(db: SessionDep):
    predictions = db.exec(
        select(MatchPrediction).where(MatchPrediction.match_date == date.today())
    ).all()

    if not predictions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No predictions available for today yet.",
        )

    return max(predictions, key=lambda p: max(p.home_win_prob, p.away_win_prob))


@router.get(
    "/predictions/today/value-bets",
    response_model=List[MatchPredictionRead],
    summary="Get today's matches where there is a positive EV bet",
    description=(
        "Returns only matches where the casino odds imply a positive Expected Value "
        "based on the ML model's probabilities. Sorted by highest EV first."
    ),
)
async def get_value_bets_today(db: SessionDep):
    predictions = db.exec(
        select(MatchPrediction).where(
            MatchPrediction.match_date == date.today(),
            MatchPrediction.best_bet.is_not(None),
        )
    ).all()

    if not predictions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No value bets found for today. "
                   "Either no odds are loaded yet or no match has a positive EV.",
        )

    # Sort by the EV of the recommended bet, highest first
    ev_map = {"home_win": "ev_home", "draw": "ev_draw", "away_win": "ev_away"}
    predictions.sort(
        key=lambda p: getattr(p, ev_map.get(p.best_bet, "ev_home"), 0) or 0,
        reverse=True,
    )

    return predictions


@router.get(
    "/predictions",
    response_model=List[MatchPredictionRead],
    summary="List all cached predictions",
)
async def list_predictions(
    db: SessionDep,
    match_date: Optional[date] = Query(None, description="Filter by a specific date"),
    home_team: Optional[str] = Query(None, description="Filter by home team name"),
    away_team: Optional[str] = Query(None, description="Filter by away team name"),
    value_bets_only: bool = Query(False, description="Return only matches with a positive EV bet"),
    offset: int = 0,
    limit: int = Query(default=10, le=100),
):
    query = select(MatchPrediction)

    if match_date:
        query = query.where(MatchPrediction.match_date == match_date)
    if home_team:
        query = query.where(MatchPrediction.home_team.ilike(f"%{home_team}%"))
    if away_team:
        query = query.where(MatchPrediction.away_team.ilike(f"%{away_team}%"))
    if value_bets_only:
        query = query.where(MatchPrediction.best_bet.is_not(None))

    query = query.order_by(MatchPrediction.match_date.desc(), MatchPrediction.id)
    return db.exec(query.offset(offset).limit(limit)).all()


@router.get(
    "/predictions/{prediction_id}",
    response_model=MatchPredictionRead,
)
async def get_prediction(prediction_id: int, db: SessionDep):
    prediction = db.get(MatchPrediction, prediction_id)
    if not prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prediction with id {prediction_id} not found",
        )
    return prediction
