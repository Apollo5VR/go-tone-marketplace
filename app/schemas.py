"""Pydantic schemas for request/response validation."""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    email: str
    password: str
    name: str


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    tier: str
    created_at: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class GameResponse(BaseModel):
    id: str
    slug: str
    title: str
    description: str
    cover_image: Optional[str]
    category: str
    difficulty: int
    min_weight: int
    max_weight: int
    default_mode: int
    rating: float
    reviews_count: int
    price: float
    is_premium: bool

    class Config:
        from_attributes = True


class ReviewCreate(BaseModel):
    rating: int
    comment: Optional[str] = None


class ScoreCreate(BaseModel):
    weight: Optional[int] = None
    score: int
    reps: int = 0
    meters: float = 0.0


class WishlistAdd(BaseModel):
    game_id: str


class CategoryFilter:
    STRENGTH = "strength"
    CARDIO = "cardio"
    FLEXIBILITY = "flexibility"
    FULL_BODY = "full_body"
    ALL = "all"
