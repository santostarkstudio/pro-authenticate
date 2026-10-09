import os
from dataclasses import dataclass


def _e(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Settings:
    secret: str = _e("FG_SECRET", "dev-secret-change-me")
    db_path: str = _e("FG_DB", "data/faceguard.db")
    admin_email: str = _e("FG_ADMIN_EMAIL", "hr@company.com")
    admin_password: str = _e("FG_ADMIN_PASSWORD", "demo")
    verifier: str = _e("FG_VERIFIER", "demo")
    yolo_path: str = _e("FG_YOLO_PATH", "models/yolo_face.pt")
    cls_path: str = _e("FG_CLS_PATH", "models/liveness.keras")
    token_hours: int = int(_e("FG_TOKEN_HOURS", "8"))
    retention_days: int = int(_e("FG_RETENTION_DAYS", "90"))   # candidates and their events are erased after this; 0 = keep
    cors: str = _e("FG_CORS", "*")
    custom: str = _e("FG_CUSTOM", "")                       # "module:function" inside your own project
    project_dir: str = _e("FG_PROJECT_DIR", "model_project")
    model_cfg: str = _e("FG_MODEL_CONFIG", "models/model.json")
    bgr: bool = _e("FG_BGR", "1") == "1"                    # OpenCV projects use BGR frames
    frontend_dir: str = _e("FG_FRONTEND", os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))


settings = Settings()
