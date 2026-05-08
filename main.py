"""
Cloud Lead Generator API
Run locally: uvicorn main:app --reload
Deploy: Render/Railway/etc. with environment variables.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./leadgen.db")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
COUNTRY_SUFFIX = os.getenv("COUNTRY_SUFFIX", "India")

# Render/Supabase often provide postgres://, SQLAlchemy expects postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

GEO_URL = "https://maps.googleapis.com/maps/api/geocode/json"
SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"


class SearchRun(Base):
    __tablename__ = "search_runs"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    radius = Column(Integer, nullable=False)
    max_results = Column(Integer, nullable=False)
    total_checked = Column(Integer, default=0)
    leads_found = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    leads = relationship("Lead", back_populates="search", cascade="all, delete-orphan")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    search_id = Column(Integer, ForeignKey("search_runs.id"), nullable=True)
    business_name = Column(String(255), nullable=False)
    category = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(120), nullable=True)
    state = Column(String(120), nullable=True)
    phone = Column(String(80), nullable=True)
    maps_url = Column(Text, nullable=True)
    search_query = Column(String(255), nullable=True)
    search_location = Column(String(255), nullable=True)
    lead_status = Column(String(80), default="New")
    notes = Column(Text, default="")
    date_found = Column(Date, default=date.today)
    created_at = Column(DateTime, default=datetime.utcnow)

    search = relationship("SearchRun", back_populates="leads")


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Lead Generator API", version="1.0.0")

origins = [o.strip() for o in ALLOWED_ORIGINS.split(",")] if ALLOWED_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    location: str = Field(..., min_length=2)
    radius: int = Field(8000, ge=1000, le=50000)
    max_results: int = Field(20, ge=1, le=60)
    city: Optional[str] = None
    state: Optional[str] = None


class LeadUpdate(BaseModel):
    lead_status: Optional[str] = None
    notes: Optional[str] = None


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def gfetch(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params["key"] = GOOGLE_API_KEY
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def geocode(address: str) -> Dict[str, Any]:
    full_address = address if COUNTRY_SUFFIX.lower() in address.lower() else f"{address}, {COUNTRY_SUFFIX}"
    data = gfetch(GEO_URL, {"address": full_address})
    if data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return {"lat": loc["lat"], "lng": loc["lng"], "status": "OK"}
    return {"error": f"Geocoding failed: {data.get('status')}", "status": data.get("status")}


def search_places(query: str, lat: float, lng: float, radius: int, page_token: Optional[str] = None) -> Dict[str, Any]:
    params = {"query": query, "location": f"{lat},{lng}", "radius": radius}
    if page_token:
        params["pagetoken"] = page_token
    return gfetch(SEARCH_URL, params)


def get_details(place_id: str) -> Dict[str, Any]:
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,website,url,types",
    }
    data = gfetch(DETAIL_URL, params)
    return data.get("result", {})


def run_google_search(payload: SearchRequest) -> Dict[str, Any]:
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured on the server.")

    events: List[Dict[str, str]] = []

    def emit(msg: str, type_: str = "info") -> None:
        events.append({"type": type_, "msg": msg})

    emit(f'Geocoding "{payload.location}"...')
    geo = geocode(payload.location)
    if "error" in geo:
        return {"error": geo["error"], "events": events}

    lat, lng = geo["lat"], geo["lng"]
    emit(f"✅ Coordinates: {lat:.4f}, {lng:.4f}", "ok")

    all_places: List[Dict[str, Any]] = []
    page_token = None
    max_pages = min(3, (payload.max_results + 19) // 20)

    for page in range(max_pages):
        emit(f'Fetching page {page + 1} for "{payload.query}" near {payload.location}...')
        if page_token:
            emit("Waiting 2s for Google page token...", "info")
            time.sleep(2.1)

        data = search_places(payload.query, lat, lng, payload.radius, page_token)
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            return {
                "error": f"Places search failed: {data.get('status')} — {data.get('error_message', '')}",
                "events": events,
            }

        results = data.get("results", [])
        emit(f"→ Got {len(results)} results on page {page + 1}", "ok" if results else "warn")
        all_places.extend(results)
        all_places = all_places[: payload.max_results]
        page_token = data.get("next_page_token")
        if not page_token or len(all_places) >= payload.max_results:
            break

    emit(f"Total businesses found: {len(all_places)}", "ok")

    leads: List[Dict[str, Any]] = []
    today = str(date.today())
    for i, place in enumerate(all_places):
        emit(f"Checking {i + 1}/{len(all_places)} — {place.get('name', '')[:45]}...")
        try:
            detail = get_details(place["place_id"])
            time.sleep(0.1)
            if detail.get("website"):
                continue
            leads.append({
                "name": detail.get("name", place.get("name", "")),
                "category": ", ".join([t for t in detail.get("types", []) if t not in ("point_of_interest", "establishment")][:3]),
                "address": detail.get("formatted_address", place.get("formatted_address", "")),
                "phone": detail.get("formatted_phone_number", ""),
                "mapsUrl": detail.get("url", f"https://www.google.com/maps/place/?q=place_id:{place['place_id']}"),
                "city": payload.city or "",
                "state": payload.state or "",
                "date": today,
            })
            emit(f"✅ [{len(leads)}] {leads[-1]['name']} — no website", "ok")
        except Exception as exc:  # noqa: BLE001
            emit(f"⚠️ Skipped {place.get('name', '')}: {exc}", "warn")

    emit(f"✅ Done! {len(leads)} leads without websites out of {len(all_places)} checked.", "ok")
    return {"leads": leads, "events": events, "total_checked": len(all_places)}


@app.get("/")
def home() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "key_set": bool(GOOGLE_API_KEY), "database": "connected"}


@app.post("/search")
def search(payload: SearchRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    result = run_google_search(payload)
    if result.get("error"):
        return result

    search_run = SearchRun(
        query=payload.query,
        location=payload.location,
        radius=payload.radius,
        max_results=payload.max_results,
        total_checked=result.get("total_checked", 0),
        leads_found=len(result.get("leads", [])),
    )
    db.add(search_run)
    db.flush()

    saved_leads = []
    for item in result.get("leads", []):
        lead = Lead(
            search_id=search_run.id,
            business_name=item.get("name", ""),
            category=item.get("category", ""),
            address=item.get("address", ""),
            city=item.get("city", ""),
            state=item.get("state", ""),
            phone=item.get("phone", ""),
            maps_url=item.get("mapsUrl", ""),
            search_query=payload.query,
            search_location=payload.location,
        )
        db.add(lead)
        db.flush()
        item["id"] = lead.id
        saved_leads.append(item)

    db.commit()
    result["search_id"] = search_run.id
    result["leads"] = saved_leads
    return result


@app.get("/leads")
def list_leads(
    db: Session = Depends(get_db),
    q: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    query = db.query(Lead).order_by(Lead.created_at.desc())
    if q:
        like = f"%{q}%"
        query = query.filter((Lead.business_name.ilike(like)) | (Lead.search_query.ilike(like)) | (Lead.address.ilike(like)))
    if city:
        query = query.filter(Lead.city.ilike(city))
    if state:
        query = query.filter(Lead.state.ilike(state))
    if status:
        query = query.filter(Lead.lead_status.ilike(status))

    rows = query.limit(limit).all()
    return {"leads": [serialize_lead(row) for row in rows]}


@app.patch("/leads/{lead_id}")
def update_lead(lead_id: int, payload: LeadUpdate, db: Session = Depends(get_db)) -> Dict[str, Any]:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if payload.lead_status is not None:
        lead.lead_status = payload.lead_status
    if payload.notes is not None:
        lead.notes = payload.notes
    db.commit()
    db.refresh(lead)
    return serialize_lead(lead)


def serialize_lead(lead: Lead) -> Dict[str, Any]:
    return {
        "id": lead.id,
        "business_name": lead.business_name,
        "category": lead.category,
        "address": lead.address,
        "city": lead.city,
        "state": lead.state,
        "phone": lead.phone,
        "maps_url": lead.maps_url,
        "search_query": lead.search_query,
        "search_location": lead.search_location,
        "lead_status": lead.lead_status,
        "notes": lead.notes,
        "date_found": str(lead.date_found) if lead.date_found else "",
        "created_at": lead.created_at.isoformat() if lead.created_at else "",
    }
