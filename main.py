import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from database import db, create_document, get_documents
from schemas import Users, Characters, Courses, Modules, Attempts, Levels, Recommendations, StoryChapters, LoginSessions

app = FastAPI(title="Adaptive LMS RPG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------
# Utility functions
# ------------------------

SALT = os.getenv("PASSWORD_SALT", "flames_salt")
SESSION_TTL_MIN = 60 * 24  # 24 hours


def hash_password(password: str) -> str:
    return hashlib.sha256((SALT + password).encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "student"  # student | teacher | admin
    selected_language: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    role: str
    redirect: str


class AttemptRequest(BaseModel):
    user_id: str
    module_id: str
    score: float  # 0-100
    time_spent: int  # seconds
    format_used: Optional[str] = None
    device_type: Optional[str] = None


class LevelUpRequest(BaseModel):
    user_id: str


def auth_required(authorization: Optional[str] = Header(None)) -> dict:
    # Expect header: Authorization: Bearer <token>
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.split(" ")[1]
    sess = db["loginsessions"].find_one({"session_token": token, "is_active": True})
    if not sess:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = db["users"].find_one({"_id": sess["user"]}) if isinstance(sess.get("user"), dict) else db["users"].find_one({"_id": sess.get("user")})
    # In our create flow we store user as string id
    if not user:
        user = db["users"].find_one({"_id": sess.get("user")})
    # Touch last activity
    db["loginsessions"].update_one({"session_token": token}, {"$set": {"last_activity": datetime.utcnow()}})
    return {"token": token, "session": sess, "user": user}


# ------------------------
# Health routes
# ------------------------

@app.get("/")
def read_root():
    return {"message": "Adaptive LMS RPG API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# ------------------------
# Seed data
# ------------------------

def seed_if_empty():
    if db is None:
        return
    # Characters
    if db["characters"].count_documents({}) == 0:
        chars = [
            {
                "name": "Sir Tagalot",
                "avatar_url": "https://i.imgur.com/9v4zK8U.png",
                "primary_color": "#e34c26",
                "accent_color": "#f59e0b",
                "special_trait": "HTML mastery",
                "starting_level": 1,
                "skill_tree": {"agility": 5, "logic": 5, "creativity": 4},
            },
            {
                "name": "Pything Serpent",
                "avatar_url": "https://i.imgur.com/2l7H0kB.png",
                "primary_color": "#3776ab",
                "accent_color": "#22d3ee",
                "special_trait": "Python wisdom",
                "starting_level": 1,
                "skill_tree": {"agility": 4, "logic": 6, "creativity": 5},
            },
        ]
        db["characters"].insert_many(chars)

    # Levels
    if db["levels"].count_documents({}) == 0:
        levels = [
            {"level_number": 1, "xp_threshold": 0, "badge_title": "Novice", "unlocks": "Welcome Pack", "level_color": "#10b981"},
            {"level_number": 2, "xp_threshold": 500, "badge_title": "Apprentice", "unlocks": "New Quests", "level_color": "#0ea5e9"},
            {"level_number": 3, "xp_threshold": 1000, "badge_title": "Adept", "unlocks": "Boss Battle", "level_color": "#f59e0b"},
            {"level_number": 4, "xp_threshold": 2000, "badge_title": "Expert", "unlocks": "Epic Loot", "level_color": "#d97706"},
            {"level_number": 5, "xp_threshold": 4000, "badge_title": "Master", "unlocks": "Legend Rank", "level_color": "#ef4444"},
        ]
        db["levels"].insert_many(levels)

    # Courses & Modules minimal seed across languages (HTML & Python fully for L1-L2)
    if db["courses"].count_documents({}) == 0:
        courses = [
            {"title": "Castle of Code", "description": "HTML Path", "category": "HTML", "difficulty_level": 1, "category_color": "#e34c26", "estimated_hours": 12},
            {"title": "Forest of Python", "description": "Python Path", "category": "Python", "difficulty_level": 1, "category_color": "#3776ab", "estimated_hours": 14},
            {"title": "Village of Java", "description": "Java Path", "category": "Java", "difficulty_level": 1, "category_color": "#f89820", "estimated_hours": 16},
            {"title": "Forge of C++", "description": "C++ Path", "category": "C++", "difficulty_level": 1, "category_color": "#6295cb", "estimated_hours": 18},
            {"title": "Tower of Interactivity", "description": "JavaScript Path", "category": "JavaScript", "difficulty_level": 1, "category_color": "#f7df1e", "estimated_hours": 16},
            {"title": "Dungeon of Servers", "description": "PHP Path", "category": "PHP", "difficulty_level": 1, "category_color": "#8892bf", "estimated_hours": 16},
        ]
        res = db["courses"].insert_many(courses)
        course_ids = dict(zip([c["category"] for c in courses], res.inserted_ids))

        def m(title, course_cat, ctype, diff, xp, narrative, url, badge, mins, topic):
            return {
                "title": title,
                "course": str(course_ids[course_cat]),
                "content_type": ctype,
                "difficulty_level": diff,
                "xp_reward": xp,
                "prerequisite_modules": [],
                "narrative_text": narrative,
                "content_url": url,
                "unlock_badge": badge,
                "estimated_time_minutes": mins,
                "topic": topic,
            }

        modules = [
            # HTML Level 1
            m("The <html> Foundation Stone", "HTML", "video", 1, 50, "Begin your journey at the Castle of Code.", "https://youtu.be/UB1O30fR-EE", "HTML Apprentice", 8, "tags"),
            m("Tag Hierarchy Challenge", "HTML", "quiz", 1, 50, "Prove your mettle with tags.", "https://gist.github.com/quiz-html-tags.json", None, 10, "tags"),
            m("Building Your First Wall", "HTML", "text", 1, 50, "Craft your first page.", "https://www.w3schools.com/html/html_basic.asp", None, 12, "structure"),
            # HTML Level 2
            m("Form Validation Dungeon", "HTML", "game", 2, 100, "Defeat the bug trolls.", "https://codepen.io/collection/forms", None, 15, "forms"),
            m("Input Types Arsenal", "HTML", "video", 2, 100, "Gather the input relics.", "https://youtu.be/fNcJuPIZ2WE", None, 12, "forms"),
            m("Radio vs Checkbox Battle", "HTML", "quiz", 2, 100, "Choose wisely.", "https://gist.github.com/quiz-radio-checkbox.json", None, 10, "forms"),
            # Python Level 1
            m("The Ancient print() Scroll", "Python", "video", 1, 50, "Awaken the serpent wisdom.", "https://youtu.be/kqtD5dpn9C8", "Python Druid", 10, "variables"),
            m("Variable Naming Ritual", "Python", "quiz", 1, 50, "Name with care.", "https://gist.github.com/quiz-naming.json", None, 8, "variables"),
            m("Data Type Collector", "Python", "game", 1, 50, "Collect the runes.", "https://codecombat.com/", None, 12, "types"),
            # Python Level 2
            m("For-Loop Vine Swinging", "Python", "video", 2, 100, "Traverse the canopy.", "https://youtu.be/OnDr4J2UXSA", None, 12, "loops"),
            m("If-Elif-Else Pathfinding", "Python", "text", 2, 100, "Find your route.", "https://realpython.com/python-conditional-statements/", None, 14, "conditions"),
            m("Break & Continue Traps", "Python", "quiz", 2, 100, "Avoid the traps.", "https://gist.github.com/quiz-break-continue.json", None, 10, "loops"),
        ]
        db["modules"].insert_many(modules)

    # Story chapters minimal
    if db["storychapters"].count_documents({}) == 0:
        chapters = [
            {"chapter_number": 1, "language_path": "HTML", "title": "Castle Gates", "description": "Enter the Castle of Code."},
            {"chapter_number": 1, "language_path": "Python", "title": "Forest Edge", "description": "Meet the Python druids."},
        ]
        db["storychapters"].insert_many(chapters)


seed_if_empty()

# ------------------------
# Authentication
# ------------------------

@app.post("/api/register", response_model=LoginResponse)
def register(payload: RegisterRequest):
    if db["users"].find_one({"email": payload.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    # Assign default character
    char = db["characters"].find_one({"name": "Sir Tagalot"}) or db["characters"].find_one({})
    user_doc = Users(
        name=payload.name,
        email=str(payload.email),
        role=payload.role,
        hashed_password=hash_password(payload.password),
        login_attempts=0,
        two_fa_enabled=False,
        current_level=1,
        xp_points=0,
        assigned_character=str(char.get("_id")) if char else None,
        preferred_format=None,
        selected_language=payload.selected_language or "HTML",
        theme_color="#0ea5e9",
        last_login=datetime.utcnow(),
    ).model_dump()

    res_id = db["users"].insert_one(user_doc).inserted_id

    token = secrets.token_urlsafe(32)
    session = LoginSessions(
        user=str(res_id), session_token=token, ip_address=None, device_type=None
    ).model_dump()
    db["loginsessions"].insert_one(session)

    redirect = "/student" if payload.role == "student" else ("/teacher" if payload.role == "teacher" else "/admin")

    return LoginResponse(token=token, role=payload.role, redirect=redirect)


@app.post("/api/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    user = db["users"].find_one({"email": str(payload.email)})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, user.get("hashed_password", "")):
        db["users"].update_one({"_id": user["_id"]}, {"$inc": {"login_attempts": 1}})
        raise HTTPException(status_code=401, detail="Invalid credentials")

    db["users"].update_one({"_id": user["_id"]}, {"$set": {"last_login": datetime.utcnow(), "login_attempts": 0}})

    token = secrets.token_urlsafe(32)
    sess = LoginSessions(user=str(user["_id"]), session_token=token).model_dump()
    db["loginsessions"].insert_one(sess)

    role = user.get("role", "student")
    redirect = "/student" if role == "student" else ("/teacher" if role == "teacher" else "/admin")
    return LoginResponse(token=token, role=role, redirect=redirect)


@app.post("/api/logout")
def logout(auth=Depends(auth_required)):
    token = auth["token"]
    db["loginsessions"].update_one({"session_token": token}, {"$set": {"is_active": False}})
    return {"success": True}


# ------------------------
# Content
# ------------------------

@app.get("/api/courses")
def list_courses(selected_language: Optional[str] = Query(None)):
    query = {}
    if selected_language:
        query["category"] = selected_language
    courses = list(db["courses"].find(query))
    for c in courses:
        c["_id"] = str(c["_id"])
    return courses


@app.get("/api/modules")
def list_modules(course_id: str):
    mods = list(db["modules"].find({"course": course_id}))
    for m in mods:
        m["_id"] = str(m["_id"])
    return mods


@app.get("/api/story_chapters")
def list_story_chapters(user_id: Optional[str] = None, language_path: Optional[str] = None):
    query = {}
    if language_path:
        query["language_path"] = language_path
    chapters = list(db["storychapters"].find(query).sort("chapter_number", 1))
    for ch in chapters:
        ch["_id"] = str(ch["_id"])
    return chapters


# ------------------------
# Gameplay & Adaptive Logic
# ------------------------

def get_next_difficulty(current: int, mastery: float) -> int:
    if mastery > 80:
        return min(5, current + 1)
    if mastery < 50:
        return max(1, current - 1)
    return current


def suggested_format_from_scores(user_id: str) -> Optional[str]:
    # compute average score per format from last 20 attempts
    attempts = list(db["attempts"].find({"user": user_id}).sort("timestamp", -1).limit(20))
    if not attempts:
        return None
    agg: Dict[str, List[float]] = {}
    for a in attempts:
        fmt = a.get("format_used") or "unknown"
        agg.setdefault(fmt, []).append(float(a.get("score", 0)))
    best, best_avg = None, -1
    for fmt, scores in agg.items():
        avg = sum(scores) / max(1, len(scores))
        if avg > best_avg:
            best, best_avg = fmt, avg
    return best if best != "unknown" else None


@app.post("/api/attempts")
def submit_attempt(payload: AttemptRequest):
    # Record attempt
    mod = db["modules"].find_one({"_id": db["modules"].database.client.get_default_database().decode_named_subcollection_name(payload.module_id)}) if False else db["modules"].find_one({"_id": None})
    # Flexible: module stored by string id, so direct find by _id string using $toObjectId
    from bson import ObjectId
    try:
        mod = db["modules"].find_one({"_id": ObjectId(payload.module_id)})
    except Exception:
        mod = None
    if not mod:
        raise HTTPException(status_code=404, detail="Module not found")

    attempt_doc = Attempts(
        user=payload.user_id,
        module=payload.module_id,
        score=payload.score,
        time_spent=payload.time_spent,
        format_used=payload.format_used,
        device_type=payload.device_type,
        completion_status="completed",
    ).model_dump()
    db["attempts"].insert_one(attempt_doc)

    # Award XP
    xp_gain = int(mod.get("difficulty_level", 1)) * 50
    user = db["users"].find_one({"_id": ObjectId(payload.user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_xp = int(user.get("xp_points", 0)) + xp_gain
    db["users"].update_one({"_id": user["_id"]}, {"$set": {"xp_points": new_xp}})

    # Level check
    levels = list(db["levels"].find({}).sort("level_number", 1))
    next_level_num = int(user.get("current_level", 1)) + 1
    next_level = next((lv for lv in levels if lv.get("level_number") == next_level_num), None)
    leveled_up = False
    if next_level and new_xp >= int(next_level.get("xp_threshold", 0)):
        db["users"].update_one({"_id": user["_id"]}, {"$set": {"current_level": next_level_num, "theme_color": next_level.get("level_color")}})
        leveled_up = True

    # Adaptive rule-based recommendation
    # mastery = (score*0.7) + (time_factor*0.3). Use inverse time: faster is better.
    # Normalize time: estimated_time_minutes * 60
    est_secs = int(mod.get("estimated_time_minutes", 10)) * 60
    time_factor = max(0.0, 100.0 - (payload.time_spent / max(1, est_secs)) * 100.0)
    mastery = (payload.score * 0.7) + (time_factor * 0.3)
    next_diff = get_next_difficulty(int(mod.get("difficulty_level", 1)), mastery)

    # Preferred format update
    pref_fmt = suggested_format_from_scores(payload.user_id) or payload.format_used
    if pref_fmt:
        db["users"].update_one({"_id": user["_id"]}, {"$set": {"preferred_format": pref_fmt}})

    # Choose next module in same course with next_diff else fallback same diff
    mods_same_course = list(db["modules"].find({"course": mod.get("course")}).sort("difficulty_level", 1))
    next_mod = next((mm for mm in mods_same_course if int(mm.get("difficulty_level", 1)) == next_diff and str(mm.get("_id")) != payload.module_id), None)
    if not next_mod:
        next_mod = next((mm for mm in mods_same_course if int(mm.get("difficulty_level", 1)) >= next_diff and str(mm.get("_id")) != payload.module_id), None)
    reason = f"Based on mastery {mastery:.1f}% and performance."

    rec_doc = Recommendations(
        user=payload.user_id,
        suggested_module=str(next_mod.get("_id")) if next_mod else None,
        suggested_format=pref_fmt or mod.get("content_type"),
        reason=reason,
        previous_attempt_score=payload.score,
        confidence_score=round(mastery / 100.0, 2),
        status="Ready",
    ).model_dump()
    db["recommendations"].insert_one(rec_doc)

    return {
        "xp_gained": xp_gain,
        "new_xp": new_xp,
        "leveled_up": leveled_up,
        "next_module_id": str(next_mod.get("_id")) if next_mod else None,
        "preferred_format": pref_fmt,
        "mastery": mastery,
    }


@app.get("/api/recommendations")
def get_recommendations(user_id: str, status: Optional[str] = None):
    query = {"user": user_id}
    if status:
        query["status"] = status
    recs = list(db["recommendations"].find(query).sort("created_at", -1).limit(10))
    for r in recs:
        r["_id"] = str(r["_id"])
    return recs


@app.put("/api/users/levelup")
def level_up(payload: LevelUpRequest):
    from bson import ObjectId
    user = db["users"].find_one({"_id": ObjectId(payload.user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    current = int(user.get("current_level", 1))
    next_level = current + 1
    lvl = db["levels"].find_one({"level_number": next_level})
    if not lvl:
        raise HTTPException(status_code=400, detail="Max level reached")
    db["users"].update_one({"_id": user["_id"]}, {"$set": {"current_level": next_level, "theme_color": lvl.get("level_color")}})
    return {"current_level": next_level}


# ------------------------
# Analytics (simplified)
# ------------------------

@app.get("/api/analytics/student/{user_id}")
def analytics_student(user_id: str):
    from bson import ObjectId
    user = db["users"].find_one({"_id": ObjectId(user_id)})
    attempts = list(db["attempts"].find({"user": user_id}).sort("timestamp", -1).limit(50))
    mastery_topics: Dict[str, List[float]] = {}
    for a in attempts:
        mod = db["modules"].find_one({"_id": ObjectId(a["module"])})
        topic = mod.get("topic") if mod else "general"
        mastery_topics.setdefault(topic, []).append(float(a.get("score", 0)))
    mastery_avg = {k: (sum(v) / len(v)) for k, v in mastery_topics.items()}
    badges = []  # MVP placeholder
    return {
        "user": {"name": user.get("name"), "level": user.get("current_level"), "xp": user.get("xp_points")},
        "mastery": mastery_avg,
        "badges": badges,
        "attempts_count": len(attempts),
    }


@app.get("/api/analytics/teacher/overview")
def analytics_teacher_overview():
    students = list(db["users"].find({"role": "student"}))
    for s in students:
        s["_id"] = str(s["_id"])
    total_attempts = db["attempts"].count_documents({})
    return {"students": len(students), "attempts": total_attempts}


@app.get("/api/analytics/admin/system")
def analytics_admin_system():
    return {
        "users": db["users"].count_documents({}),
        "active_sessions": db["loginsessions"].count_documents({"is_active": True}),
        "courses": db["courses"].count_documents({}),
        "modules": db["modules"].count_documents({}),
        "attempts": db["attempts"].count_documents({}),
    }


# ------------------------
# Admin & Teacher helpers (MVP)
# ------------------------

class GrantXPRequest(BaseModel):
    user_id: str
    xp: int


@app.post("/api/teacher/grant_xp")
def grant_xp(req: GrantXPRequest):
    from bson import ObjectId
    user = db["users"].find_one({"_id": ObjectId(req.user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_xp = int(user.get("xp_points", 0)) + int(req.xp)
    db["users"].update_one({"_id": user["_id"]}, {"$set": {"xp_points": new_xp}})
    return {"xp_points": new_xp}


# ------------------------
# RL Agent contract (stub)
# ------------------------

class RLRequest(BaseModel):
    user_id: str
    recent_attempts: List[Dict[str, Any]]
    skill_tree: Dict[str, int]


class RLResponse(BaseModel):
    suggested_module_id: Optional[str] = None
    format: Optional[str] = None
    reason: Optional[str] = None
    confidence: Optional[float] = None


@app.post("/api/recommend", response_model=RLResponse)
def recommend_rl(_: RLRequest):
    # V1: Not implemented, return empty to trigger rule-based fallback in frontend/clients
    return RLResponse(suggested_module_id=None, format=None, reason="Rule-based fallback", confidence=0.0)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
