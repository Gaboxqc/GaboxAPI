from datetime import date, datetime
from typing import List, Optional, Literal

from pydantic import BaseModel
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


# ==============================================================================
# ML API RESPONSE SCHEMAS  (Pydantic only — never stored directly)
# ==============================================================================

class MLExpectedGoals(BaseModel):
    home: float
    away: float


class MLTeamInfo(BaseModel):
    home_elo: float
    away_elo: float
    elo_diff: float
    h2h_games: int
    h2h_home_wins: float


class MLMatchResult(BaseModel):
    home_win: float
    draw: float
    away_win: float


class MLOverUnder(BaseModel):
    over_1_5: float
    over_2_5: float
    over_3_5: float


class MLBtts(BaseModel):
    yes: float
    no: float


class MLPredictionResponse(BaseModel):
    home_team: str
    away_team: str
    expected_goals: MLExpectedGoals
    team_info: MLTeamInfo
    model_version: str
    match_result: MLMatchResult
    over_under: MLOverUnder
    btts: MLBtts


# ==============================================================================
# REQUEST SCHEMAS
# ==============================================================================

class MatchPredictionCreate(SQLModel):
    """Single match — used for manual override only."""
    home_team: str = Field(min_length=2)
    away_team: str = Field(min_length=2)
    match_date: Optional[date] = None
    is_neutral: bool = True
    odds_home: Optional[float] = Field(default=None, gt=1.0)
    odds_draw: Optional[float] = Field(default=None, gt=1.0)
    odds_away: Optional[float] = Field(default=None, gt=1.0)
    home_flag_url: Optional[str] = None
    away_flag_url: Optional[str] = None


class MatchPredictionBatchCreate(SQLModel):
    """Manual batch — used when you want to override what the sync fetches."""
    matches: List[MatchPredictionCreate]
    match_date: Optional[date] = None


class MatchResultUpdate(SQLModel):
    """Posted by admin after the match ends to record the real outcome."""
    actual_result: Literal["home_win", "draw", "away_win"]


# ==============================================================================
# TABLE MODEL
# ==============================================================================

class MatchPrediction(SQLModel, table=True):
    __tablename__: str = "statpitch_match_prediction"
    __table_args__ = (
        UniqueConstraint("match_date", "home_team", "away_team", name="uq_match_date_teams"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    # Match identity
    match_date: date = Field(index=True)
    home_team: str
    away_team: str
    is_neutral: bool = Field(default=True)
    home_flag_url: Optional[str] = Field(default=None)
    away_flag_url: Optional[str] = Field(default=None)
    model_version: str
    predicted_at: datetime = Field(default_factory=datetime.utcnow)

    # Expected Goals
    home_xg: float
    away_xg: float

    # Team Info
    home_elo: float
    away_elo: float
    elo_diff: float
    h2h_games: int
    h2h_home_wins: float

    # Match Result probabilities (from ML model)
    home_win_prob: float
    draw_prob: float
    away_win_prob: float

    # Over/Under
    over_1_5: float
    over_2_5: float
    over_3_5: float

    # BTTS
    btts_yes: float
    btts_no: float

    # Casino odds (fetched automatically from The Odds API)
    odds_home: Optional[float] = Field(default=None)
    odds_draw: Optional[float] = Field(default=None)
    odds_away: Optional[float] = Field(default=None)

    # Expected Value — computed from probabilities × odds
    # EV > 0 means the casino is undervaluing that outcome
    ev_home: Optional[float] = Field(default=None)
    ev_draw: Optional[float] = Field(default=None)
    ev_away: Optional[float] = Field(default=None)

    # Best outcome to bet on (highest positive EV), None if no value found
    best_bet: Optional[str] = Field(default=None)  # "home_win" | "draw" | "away_win" | None

    # Actual result — filled in after the match ends
    actual_result: Optional[str] = Field(default=None)


# ==============================================================================
# READ SCHEMAS
# ==============================================================================

class MatchPredictionRead(SQLModel):
    id: int
    match_date: date
    home_team: str
    away_team: str
    is_neutral: bool
    home_flag_url: Optional[str]
    away_flag_url: Optional[str]
    model_version: str
    predicted_at: datetime
    home_xg: float
    away_xg: float
    home_elo: float
    away_elo: float
    elo_diff: float
    h2h_games: int
    h2h_home_wins: float
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    over_1_5: float
    over_2_5: float
    over_3_5: float
    btts_yes: float
    btts_no: float
    odds_home: Optional[float]
    odds_draw: Optional[float]
    odds_away: Optional[float]
    ev_home: Optional[float]
    ev_draw: Optional[float]
    ev_away: Optional[float]
    best_bet: Optional[str]
    actual_result: Optional[str]


class DailyStatsRead(SQLModel):
    predictions_today: int
    high_confidence_today: int
    high_confidence_threshold: float
    value_bets_today: int
    accuracy_30d: Optional[float]
    roi_30d: Optional[float]
    settled_matches_30d: int


class SyncResultRead(SQLModel):
    """Summary returned after a /sync call."""
    synced: int           # matches successfully fetched + stored
    skipped: int          # already cached, not overwritten
    date: date
    matches: List[MatchPredictionRead]
