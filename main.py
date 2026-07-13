"""
Cloud Lead Generator API
Run locally: uvicorn main:app --reload
Deploy: Render/Railway/etc. with environment variables.
"""
from __future__ import annotations

import os
import re
import time
import traceback
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Date, Float, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./leadgen.db")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
COUNTRY_SUFFIX = os.getenv("COUNTRY_SUFFIX", "India")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

GEO_URL    = "https://maps.googleapis.com/maps/api/geocode/json"
SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
DETAIL_URL = "https://maps.googleapis.com/maps/api/place/details/json"

SOCIAL_PATTERNS = {
    "facebook":  r'facebook\.com/(?!sharer|share|plugins|dialog)',
    "instagram": r'instagram\.com/',
    "linkedin":  r'linkedin\.com/(?:company|in|pub)/',
    "youtube":   r'youtube\.com/(?:channel|c|user|@)',
    "twitter":   r'(?:twitter|x)\.com/',
}

# ── MODELS ────────────────────────────────────────────────────────────────

class SearchRun(Base):
    __tablename__ = "search_runs"
    id            = Column(Integer, primary_key=True, index=True)
    query         = Column(String(255), nullable=False)
    location      = Column(String(255), nullable=False)
    radius        = Column(Integer, nullable=False)
    max_results   = Column(Integer, nullable=False)
    total_checked = Column(Integer, default=0)
    leads_found   = Column(Integer, default=0)
    mode          = Column(String(20), default="no_website")
    created_at    = Column(DateTime, default=datetime.utcnow)
    leads = relationship("Lead", back_populates="search", cascade="all, delete-orphan")


class Lead(Base):
    __tablename__ = "leads"
    id             = Column(Integer, primary_key=True, index=True)
    search_id      = Column(Integer, ForeignKey("search_runs.id"), nullable=True)
    mode           = Column(String(20), default="no_website")
    business_name  = Column(String(255), nullable=False)
    category       = Column(Text, nullable=True)
    address        = Column(Text, nullable=True)
    city           = Column(String(120), nullable=True)
    state          = Column(String(120), nullable=True)
    phone          = Column(String(80), nullable=True)
    maps_url       = Column(Text, nullable=True)
    website        = Column(Text, nullable=True)
    rating         = Column(Float, nullable=True)
    review_count   = Column(Integer, nullable=True)
    has_meta_title = Column(String(10), nullable=True)
    has_meta_desc  = Column(String(10), nullable=True)
    has_h1         = Column(String(10), nullable=True)
    has_schema     = Column(String(10), nullable=True)
    socials_found  = Column(Text, nullable=True)
    score_aeo      = Column(Integer, nullable=True)
    score_seo      = Column(Integer, nullable=True)
    score_ads      = Column(Integer, nullable=True)
    score_social   = Column(Integer, nullable=True)
    score_redesign = Column(Integer, nullable=True)
    overall_score  = Column(Integer, nullable=True)
    top_pitch      = Column(String(120), nullable=True)
    search_query   = Column(String(255), nullable=True)
    search_location= Column(String(255), nullable=True)
    lead_status    = Column(String(80), default="New")
    notes          = Column(Text, default="")
    date_found     = Column(Date, default=date.today)
    created_at     = Column(DateTime, default=datetime.utcnow)
    search = relationship("SearchRun", back_populates="leads")


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Lead Generator API", version="2.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

origins = [o.strip() for o in ALLOWED_ORIGINS.split(",")] if ALLOWED_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── SCHEMAS ───────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query:       str = Field(..., min_length=2)
    location:    str = Field(..., min_length=2)
    radius:      int = Field(8000, ge=1000, le=50000)
    max_results: int = Field(20, ge=1, le=60)
    mode:        str = Field("no_website")
    min_reviews: int = Field(0, ge=0, le=10000)
    search_all:  bool = Field(False)
    city:        Optional[str] = None
    state:       Optional[str] = None
    country:     Optional[str] = None
    area:        Optional[str] = None


class LeadUpdate(BaseModel):
    lead_status: Optional[str] = None
    notes:       Optional[str] = None


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── GOOGLE HELPERS ────────────────────────────────────────────────────────

def gfetch(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params["key"] = GOOGLE_API_KEY
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def geocode(address: str, country: Optional[str] = None) -> Dict[str, Any]:
    suffix = country or COUNTRY_SUFFIX
    full_address = address if suffix.lower() in address.lower() else f"{address}, {suffix}"
    data = gfetch(GEO_URL, {"address": full_address})
    if data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return {"lat": loc["lat"], "lng": loc["lng"], "status": "OK"}
    return {"error": f"Geocoding failed: {data.get('status')}", "status": data.get("status")}


def search_places(query: str, lat: float, lng: float, radius: int,
                  page_token: Optional[str] = None) -> Dict[str, Any]:
    params = {"query": query, "location": f"{lat},{lng}", "radius": radius}
    if page_token:
        params["pagetoken"] = page_token
    return gfetch(SEARCH_URL, params)


def search_places_nearby(lat: float, lng: float, radius: int,
                          page_token: Optional[str] = None) -> Dict[str, Any]:
    """Fetch ALL businesses near a point, no category/keyword required."""
    params = {"location": f"{lat},{lng}", "radius": radius, "type": "establishment"}
    if page_token:
        params["pagetoken"] = page_token
    return gfetch(NEARBY_URL, params)


def get_details(place_id: str) -> Dict[str, Any]:
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,website,url,types,rating,user_ratings_total",
    }
    data = gfetch(DETAIL_URL, params)
    return data.get("result", {})

# ── WEBSITE AUDITOR ───────────────────────────────────────────────────────

def audit_website(url: str) -> Dict[str, Any]:
    result = {
        "reachable":      False,
        "has_meta_title": "no",
        "has_meta_desc":  "no",
        "has_h1":         "no",
        "has_schema":     "no",
        "socials_found":  [],
    }
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LeadGenBot/2.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if resp.status_code >= 400:
            return result
        html = resp.text
        result["reachable"] = True

        if re.search(r'<title[^>]*>[^<]{3,}</title>', html, re.I):
            result["has_meta_title"] = "yes"

        if re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'][^"\']{10,}', html, re.I) or \
           re.search(r'<meta[^>]+content=["\'][^"\']{10,}[^>]+name=["\']description["\']', html, re.I):
            result["has_meta_desc"] = "yes"

        if re.search(r'<h1[^>]*>[^<]{2,}</h1>', html, re.I):
            result["has_h1"] = "yes"

        if re.search(r'application/ld\+json', html, re.I) or \
           re.search(r'itemtype=["\']https?://schema\.org', html, re.I):
            result["has_schema"] = "yes"

        found = []
        for platform, pattern in SOCIAL_PATTERNS.items():
            if re.search(pattern, html, re.I):
                found.append(platform)
        result["socials_found"] = found

    except Exception:
        pass
    return result


def compute_scores(detail: Dict[str, Any], audit: Dict[str, Any]) -> Dict[str, Any]:
    rating       = detail.get("rating") or 0
    review_count = detail.get("user_ratings_total") or 0
    socials      = audit.get("socials_found", [])
    has_schema   = audit["has_schema"] == "yes"
    has_meta_d   = audit["has_meta_desc"] == "yes"
    has_h1       = audit["has_h1"] == "yes"
    has_title    = audit["has_meta_title"] == "yes"
    reachable    = audit["reachable"]

    # AEO/GEO — gap score: higher = more opportunity
    aeo = 100
    if has_schema:        aeo -= 30
    if has_meta_d:        aeo -= 20
    if review_count > 50: aeo -= 15
    if len(socials) >= 3: aeo -= 15
    if rating >= 4.5:     aeo -= 10
    aeo = max(aeo, 10)

    # SEO
    seo = 100
    if has_title:         seo -= 25
    if has_meta_d:        seo -= 25
    if has_h1:            seo -= 20
    if has_schema:        seo -= 15
    if not reachable:     seo = 95
    seo = max(seo, 10)

    # Google Ads
    ads = 50
    if review_count < 20:       ads += 25
    if review_count > 200:      ads -= 20
    if 3.5 <= rating <= 4.5:    ads += 10
    if rating < 3.5:            ads -= 10
    ads = max(min(ads, 100), 10)

    # Social Media
    social = max(100 - (len(socials) * 20), 10)

    # Website Redesign
    redesign = 0
    if not reachable:     redesign += 60
    if not has_schema:    redesign += 15
    if not has_meta_d:    redesign += 10
    if not has_h1:        redesign += 10
    if review_count < 10: redesign += 5
    redesign = min(redesign, 100)

    scores = {
        "score_aeo":      aeo,
        "score_seo":      seo,
        "score_ads":      ads,
        "score_social":   social,
        "score_redesign": redesign,
    }
    service_map = {
        "score_aeo":      "AEO/GEO (AI Search Visibility)",
        "score_seo":      "SEO",
        "score_ads":      "Google Ads / PPC",
        "score_social":   "Social Media Management",
        "score_redesign": "Website Redesign",
    }
    top_key   = max(scores, key=scores.get)
    top_pitch = service_map[top_key]
    overall   = round(sum(scores.values()) / len(scores))
    return {**scores, "overall_score": overall, "top_pitch": top_pitch}

# ── CORE SEARCH ───────────────────────────────────────────────────────────

def run_google_search(payload: SearchRequest) -> Dict[str, Any]:
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY is not configured on the server.")

    events: List[Dict[str, str]] = []
    def emit(msg: str, type_: str = "info") -> None:
        events.append({"type": type_, "msg": msg})

    emit(f'Geocoding "{payload.location}"...')
    geo = geocode(payload.location, payload.country)
    if "error" in geo:
        return {"error": geo["error"], "events": events}

    lat, lng = geo["lat"], geo["lng"]
    emit(f"✅ Coordinates: {lat:.4f}, {lng:.4f}", "ok")

    all_places: List[Dict[str, Any]] = []
    page_token = None
    max_pages = min(3, (payload.max_results + 19) // 20)
    search_label = "All Businesses (no category filter)" if payload.search_all else payload.query

    for page in range(max_pages):
        emit(f'Fetching page {page + 1} for "{search_label}" near {payload.location}...')
        if page_token:
            emit("Waiting for Google page token to activate...", "info")
            time.sleep(3.5)

        if payload.search_all:
            data = search_places_nearby(lat, lng, payload.radius, page_token)
        else:
            data = search_places(payload.query, lat, lng, payload.radius, page_token)

        if page_token and data.get("status") == "INVALID_REQUEST":
            emit("Page token not active yet, retrying once...", "warn")
            time.sleep(2.5)
            if payload.search_all:
                data = search_places_nearby(lat, lng, payload.radius, page_token)
            else:
                data = search_places(payload.query, lat, lng, payload.radius, page_token)

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            if page_token and all_places:
                emit(f"⚠️ Could not fetch additional results ({data.get('status')}); continuing with {len(all_places)} found so far.", "warn")
                break
            return {"error": f"Places search failed: {data.get('status')} — {data.get('error_message', '')}", "events": events}

        results = data.get("results", [])
        emit(f"→ Got {len(results)} results on page {page + 1}", "ok" if results else "warn")
        all_places.extend(results)
        all_places = all_places[: payload.max_results]
        page_token = data.get("next_page_token")
        if not page_token or len(all_places) >= payload.max_results:
            break

    emit(f"Total businesses found: {len(all_places)}", "ok")
    if payload.min_reviews:
        emit(f"Filtering to businesses with {payload.min_reviews}+ Google reviews...", "info")

    leads: List[Dict[str, Any]] = []
    today = str(date.today())
    is_has_website = payload.mode == "has_website"

    for i, place in enumerate(all_places):
        emit(f"Checking {i + 1}/{len(all_places)} — {place.get('name', '')[:45]}...")
        try:
            detail = get_details(place["place_id"])
            time.sleep(0.1)
            website      = detail.get("website", "")
            rating       = detail.get("rating")
            review_count = detail.get("user_ratings_total") or 0

            if payload.min_reviews and review_count < payload.min_reviews:
                continue

            if is_has_website:
                if not website:
                    continue
                emit(f"  🌐 {website[:60]}", "info")
                emit(f"  📊 Auditing homepage...", "info")
                audit  = audit_website(website)
                scores = compute_scores(detail, audit)
                leads.append({
                    "name":          detail.get("name", place.get("name", "")),
                    "category":      ", ".join([t for t in detail.get("types", []) if t not in ("point_of_interest", "establishment")][:3]),
                    "address":       detail.get("formatted_address", place.get("formatted_address", "")),
                    "phone":         detail.get("formatted_phone_number", ""),
                    "mapsUrl":       detail.get("url", f"https://www.google.com/maps/place/?q=place_id:{place['place_id']}"),
                    "website":       website,
                    "rating":        rating,
                    "reviewCount":   review_count,
                    "city":          payload.city or "",
                    "state":         payload.state or "",
                    "date":          today,
                    "mode":          "has_website",
                    "hasMetaTitle":  audit["has_meta_title"],
                    "hasMetaDesc":   audit["has_meta_desc"],
                    "hasH1":         audit["has_h1"],
                    "hasSchema":     audit["has_schema"],
                    "socialsFound":  ", ".join(audit["socials_found"]),
                    **scores,
                })
                emit(f"✅ [{len(leads)}] {leads[-1]['name']} — pitch: {scores['top_pitch']} ({scores['overall_score']})", "ok")
            else:
                if website:
                    continue
                leads.append({
                    "name":        detail.get("name", place.get("name", "")),
                    "category":    ", ".join([t for t in detail.get("types", []) if t not in ("point_of_interest", "establishment")][:3]),
                    "address":     detail.get("formatted_address", place.get("formatted_address", "")),
                    "phone":       detail.get("formatted_phone_number", ""),
                    "mapsUrl":     detail.get("url", f"https://www.google.com/maps/place/?q=place_id:{place['place_id']}"),
                    "rating":      rating,
                    "reviewCount": review_count,
                    "city":        payload.city or "",
                    "state":       payload.state or "",
                    "date":        today,
                    "mode":        "no_website",
                })
                emit(f"✅ [{len(leads)}] {leads[-1]['name']} — no website ({review_count} reviews)", "ok")

        except Exception as exc:
            emit(f"⚠️ Skipped {place.get('name', '')}: {exc}", "warn")

    label = "with websites (audited)" if is_has_website else "without websites"
    emit(f"✅ Done! {len(leads)} leads {label} out of {len(all_places)} checked.", "ok")
    return {"leads": leads, "events": events, "total_checked": len(all_places)}

# ── ROUTES ────────────────────────────────────────────────────────────────

@app.get("/")
def home() -> FileResponse:
    return FileResponse("static/index.html")

@app.get("/login.html")
def login_page() -> FileResponse:
    return FileResponse("static/login.html")

@app.get("/signup.html")
def signup_page() -> FileResponse:
    return FileResponse("static/signup.html")

@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "key_set": bool(GOOGLE_API_KEY), "database": "connected"}


@app.post("/search")
def search(payload: SearchRequest, db: Session = Depends(get_db)) -> Any:
    try:
        result = run_google_search(payload)
        if result.get("error"):
            return result

        search_run = SearchRun(
            query=payload.query, location=payload.location,
            radius=payload.radius, max_results=payload.max_results,
            mode=payload.mode,
            total_checked=result.get("total_checked", 0),
            leads_found=len(result.get("leads", [])),
        )
        db.add(search_run)
        db.flush()

        saved_leads = []
        for item in result.get("leads", []):
            lead = Lead(
                search_id=search_run.id, mode=item.get("mode", payload.mode),
                business_name=item.get("name", ""), category=item.get("category", ""),
                address=item.get("address", ""), city=item.get("city", ""),
                state=item.get("state", ""), phone=item.get("phone", ""),
                maps_url=item.get("mapsUrl", ""), website=item.get("website"),
                rating=item.get("rating"), review_count=item.get("reviewCount"),
                has_meta_title=item.get("hasMetaTitle"), has_meta_desc=item.get("hasMetaDesc"),
                has_h1=item.get("hasH1"), has_schema=item.get("hasSchema"),
                socials_found=item.get("socialsFound"),
                score_aeo=item.get("score_aeo"), score_seo=item.get("score_seo"),
                score_ads=item.get("score_ads"), score_social=item.get("score_social"),
                score_redesign=item.get("score_redesign"), overall_score=item.get("overall_score"),
                top_pitch=item.get("top_pitch"),
                search_query=payload.query, search_location=payload.location,
            )
            db.add(lead)
            db.flush()
            item["id"] = lead.id
            saved_leads.append(item)

        db.commit()
        result["search_id"] = search_run.id
        result["leads"]     = saved_leads
        return result

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Search failed: {str(e)}", "events": []})


@app.get("/leads")
def list_leads(
    db: Session = Depends(get_db),
    q: Optional[str] = None, city: Optional[str] = None,
    state: Optional[str] = None, status: Optional[str] = None,
    mode: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    try:
        query = db.query(Lead).order_by(Lead.created_at.desc())
        if q:
            like = f"%{q}%"
            query = query.filter(
                (Lead.business_name.ilike(like)) | (Lead.search_query.ilike(like)) | (Lead.address.ilike(like))
            )
        if city:   query = query.filter(Lead.city.ilike(city))
        if state:  query = query.filter(Lead.state.ilike(state))
        if status: query = query.filter(Lead.lead_status.ilike(status))
        if mode:   query = query.filter(Lead.mode == mode)
        rows = query.limit(limit).all()
        return {"leads": [serialize_lead(row) for row in rows]}
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Failed to load leads: {str(e)}"})


@app.patch("/leads/{lead_id}")
def update_lead(lead_id: int, payload: LeadUpdate, db: Session = Depends(get_db)) -> Any:
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Failed to update lead: {str(e)}"})


def serialize_lead(lead: Lead) -> Dict[str, Any]:
    return {
        "id": lead.id, "mode": lead.mode or "no_website",
        "business_name": lead.business_name, "category": lead.category,
        "address": lead.address, "city": lead.city, "state": lead.state,
        "phone": lead.phone, "maps_url": lead.maps_url, "website": lead.website,
        "rating": lead.rating, "review_count": lead.review_count,
        "has_meta_title": lead.has_meta_title, "has_meta_desc": lead.has_meta_desc,
        "has_h1": lead.has_h1, "has_schema": lead.has_schema,
        "socials_found": lead.socials_found,
        "score_aeo": lead.score_aeo, "score_seo": lead.score_seo,
        "score_ads": lead.score_ads, "score_social": lead.score_social,
        "score_redesign": lead.score_redesign, "overall_score": lead.overall_score,
        "top_pitch": lead.top_pitch,
        "search_query": lead.search_query, "search_location": lead.search_location,
        "lead_status": lead.lead_status, "notes": lead.notes,
        "date_found": str(lead.date_found) if lead.date_found else "",
        "created_at": lead.created_at.isoformat() if lead.created_at else "",
    }
