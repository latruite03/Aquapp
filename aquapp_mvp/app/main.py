from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from app.db import get_connection, init_db
from app.services.openai_analyze import analyze_image

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("aquapp")

BASE_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = BASE_DIR / "data" / "uploads"

ALLOWED_TYPES = {"image/jpeg", "image/png"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_SIZE_BYTES = 10 * 1024 * 1024

def _load_env() -> None:
    candidates = [BASE_DIR / ".env", BASE_DIR.parent / ".env"]
    for path in candidates:
        if path.is_file():
            load_dotenv(dotenv_path=path, override=False)
            break


_load_env()

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM photos ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "photo": row})


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    return templates.TemplateResponse(
        "upload.html", {"request": request, "error": None, "comment": ""}
    )


@app.post("/upload")
async def upload_photo(
    request: Request,
    file: UploadFile = File(...),
    comment: str = Form(""),
):
    comment_clean = comment.strip()
    if len(comment_clean) > 1000:
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "error": "Le commentaire dépasse 1000 caractères.",
                "comment": comment,
            },
            status_code=400,
        )
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if file.content_type not in ALLOWED_TYPES or extension not in ALLOWED_EXTENSIONS:
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "error": "Seuls les fichiers JPG et PNG sont autorisés.",
                "comment": comment,
            },
            status_code=400,
        )

    data = await file.read()
    if len(data) > MAX_SIZE_BYTES:
        return templates.TemplateResponse(
            "upload.html",
            {
                "request": request,
                "error": "Le fichier dépasse la limite de 10 Mo.",
                "comment": comment,
            },
            status_code=400,
        )

    created_at = datetime.utcnow().isoformat()
    photo_id = str(uuid4())
    date_folder = datetime.utcnow().strftime("%Y-%m-%d")
    target_dir = UPLOAD_DIR / date_folder
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{photo_id}{extension}"
    stored_path = target_dir / stored_name
    stored_path.write_bytes(data)
    relative_path = (Path(date_folder) / stored_name).as_posix()

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO photos (
                id, created_at, source, filename, filepath, content_type, user_comment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                photo_id,
                created_at,
                "user",
                filename,
                relative_path,
                file.content_type,
                comment_clean or None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info("Uploaded photo %s", photo_id)
    return RedirectResponse(url=f"/photo/{photo_id}", status_code=303)


@app.get("/history", response_class=HTMLResponse)
def history(request: Request):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM photos ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    finally:
        conn.close()
    return templates.TemplateResponse("history.html", {"request": request, "photos": rows})


@app.get("/photo/{photo_id}", response_class=HTMLResponse)
def photo_detail(request: Request, photo_id: str):
    conn = get_connection()
    try:
        photo = conn.execute(
            "SELECT * FROM photos WHERE id = ?", (photo_id,)
        ).fetchone()
        analysis = None
        if photo:
            analysis = conn.execute(
                """
                SELECT * FROM analyses WHERE photo_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (photo_id,),
            ).fetchone()
    finally:
        conn.close()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo introuvable")

    return templates.TemplateResponse(
        "photo.html",
        {
            "request": request,
            "photo": photo,
            "analysis": analysis,
        },
    )


@app.post("/photo/{photo_id}/analyze")
def analyze(photo_id: str):
    conn = get_connection()
    try:
        photo = conn.execute(
            "SELECT * FROM photos WHERE id = ?", (photo_id,)
        ).fetchone()
        history_rows = conn.execute(
            """
            SELECT analyses.created_at, analyses.raw_text, photos.user_comment
            FROM analyses
            JOIN photos ON photos.id = analyses.photo_id
            WHERE analyses.success = 1
            ORDER BY analyses.created_at DESC
            LIMIT 5
            """
        ).fetchall()
    finally:
        conn.close()

    if not photo:
        raise HTTPException(status_code=404, detail="Photo introuvable")

    image_path = UPLOAD_DIR / photo["filepath"]
    history = []
    for row in history_rows:
        created_at = row["created_at"]
        raw_text = row["raw_text"]
        comment = row["user_comment"]
        if not raw_text:
            continue
        parts = [f"Analyse du {created_at}:"]
        if comment:
            parts.append(f"Commentaire: {comment}")
        parts.append(raw_text)
        history.append("\n".join(parts))
    result = analyze_image(
        image_path,
        photo["filename"],
        photo["user_comment"],
        history=history or None,
    )
    analysis_id = str(uuid4())
    created_at = datetime.utcnow().isoformat()

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO analyses (id, photo_id, created_at, model, json_text, raw_text, success)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                photo_id,
                created_at,
                result.model,
                result.json_text,
                result.raw_text,
                1 if result.success else 0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if result.error_message:
        logger.warning("Analysis error for %s: %s", photo_id, result.error_message)

    return RedirectResponse(url=f"/photo/{photo_id}", status_code=303)


@app.exception_handler(404)
def not_found(request: Request, exc: HTTPException):
    return templates.TemplateResponse(
        "base.html",
        {
            "request": request,
        "content": "<h2>Page introuvable</h2><p>La page demandée n'existe pas.</p>",
        },
        status_code=404,
    )
