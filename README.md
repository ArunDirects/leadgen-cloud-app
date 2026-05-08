# Lead Generator Cloud App

Cloud-ready version of your local Lead Generator. It uses:

- FastAPI backend
- Google Geocoding + Places APIs
- PostgreSQL database, recommended free option: Supabase
- Single-page HTML dashboard
- CSV export
- Lead status and notes

## Local setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with your Google API key. For local testing, you can use SQLite by setting:

```env
DATABASE_URL=sqlite:///./leadgen.db
```

Run:

```bash
uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Supabase database setup

1. Create a free account at Supabase.
2. Create a new project.
3. Go to Project Settings > Database.
4. Copy the connection string.
5. Use it as `DATABASE_URL`.
6. Replace `[YOUR-PASSWORD]` with your real database password.

The app creates the required tables automatically on startup.

## Render deployment

1. Push this folder to GitHub.
2. Create a free Render account.
3. Click New > Web Service.
4. Connect your GitHub repository.
5. Use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables:
   - `GOOGLE_API_KEY`
   - `DATABASE_URL`
   - `ALLOWED_ORIGINS=*`
   - `COUNTRY_SUFFIX=India`
7. Deploy.

## API endpoints

- `GET /health`
- `POST /search`
- `GET /leads`
- `PATCH /leads/{lead_id}`

## Notes

Google API usage may still cost money depending on usage. Set billing alerts and API restrictions in Google Cloud.
