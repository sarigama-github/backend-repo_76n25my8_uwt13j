"""
Database Schemas for Adaptive LMS RPG

Each Pydantic model corresponds to a MongoDB collection. Collection name = lowercase class name.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# 1) Users
class Users(BaseModel):
    name: str
    email: str
    role: str = Field(..., description="student | teacher | admin")
    hashed_password: str
    login_attempts: int = 0
    two_fa_enabled: bool = False
    current_level: int = 1
    xp_points: int = 0
    assigned_character: Optional[str] = None  # character _id as string
    preferred_format: Optional[str] = None    # video | text | quiz | game
    selected_language: Optional[str] = None   # HTML | Python | Java | C++ | JavaScript | PHP
    theme_color: Optional[str] = None
    last_login: Optional[datetime] = None

# 2) Characters
class Characters(BaseModel):
    name: str
    avatar_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    special_trait: Optional[str] = None
    starting_level: int = 1
    skill_tree: Dict[str, int] = Field(default_factory=lambda: {"agility": 0, "logic": 0, "creativity": 0})

# 3) Courses
class Courses(BaseModel):
    title: str
    description: Optional[str] = None
    category: str  # HTML, Python, Java, C++, JavaScript, PHP
    difficulty_level: int = Field(ge=1, le=5)
    category_color: Optional[str] = None
    estimated_hours: Optional[int] = 0

# 4) Modules
class Modules(BaseModel):
    title: str
    course: str  # course _id as string
    content_type: str  # video | text | quiz | game
    difficulty_level: int = Field(ge=1, le=5)
    xp_reward: int = 50
    prerequisite_modules: List[str] = Field(default_factory=list)  # module ids
    narrative_text: Optional[str] = None
    content_url: Optional[str] = None
    unlock_badge: Optional[str] = None
    estimated_time_minutes: Optional[int] = 10
    topic: Optional[str] = None  # for mastery tracking

# 5) Attempts
class Attempts(BaseModel):
    user: str  # user _id
    module: str  # module _id
    score: float = 0.0  # 0-100
    time_spent: int = 0  # seconds
    format_used: Optional[str] = None
    device_type: Optional[str] = None
    completion_status: str = "completed"  # completed | abandoned
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# 6) Levels
class Levels(BaseModel):
    level_number: int
    xp_threshold: int
    badge_title: str
    unlocks: Optional[str] = None
    level_color: Optional[str] = None
    icon_url: Optional[str] = None

# 7) Recommendations
class Recommendations(BaseModel):
    user: str
    suggested_module: Optional[str] = None
    suggested_format: Optional[str] = None
    reason: Optional[str] = None
    previous_attempt_score: Optional[float] = None
    confidence_score: Optional[float] = None
    status: str = "Pending"  # Pending | Ready | Consumed
    created_at: datetime = Field(default_factory=datetime.utcnow)

# 8) StoryChapters
class StoryChapters(BaseModel):
    chapter_number: int
    language_path: str  # HTML, Python, ...
    title: str
    description: str
    unlock_condition: Optional[str] = None
    reward_type: Optional[str] = None
    reward_value: Optional[str] = None

# 9) LoginSessions
class LoginSessions(BaseModel):
    user: str
    session_token: str
    ip_address: Optional[str] = None
    device_type: Optional[str] = None
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

# 10) Notifications
class Notifications(BaseModel):
    title: str
    message: str
    audience: str = Field(default="students", description="students | teachers | admins | all")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None  # teacher/admin id
    read_by: List[str] = Field(default_factory=list)  # user ids who read

# Helper to expose schema for viewers
class SchemaInfo(BaseModel):
    name: str
    fields: Dict[str, Any]
