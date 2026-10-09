import base64

MAX_BYTES = 2_000_000


def decode_data_url(value: str) -> bytes:
    """Accepts 'data:image/jpeg;base64,....' or raw base64."""
    payload = value.split(",", 1)[1] if value.startswith("data:") else value
    data = base64.b64decode(payload, validate=False)
    if not data or len(data) > MAX_BYTES:
        raise ValueError("image missing or too large")
    return data


def get_verifier(cfg):
    """FG_VERIFIER = demo (placeholder) | custom (call a function in your project) | model (YOLO + Keras from model.json)."""
    if cfg.verifier == "custom":
        from .custom import CustomVerifier
        return CustomVerifier(cfg.custom, cfg.project_dir, cfg.bgr)
    if cfg.verifier == "model":
        from .model_adapter import ModelVerifier
        return ModelVerifier.from_json(cfg.model_cfg, cfg.yolo_path, cfg.cls_path, cfg.bgr)
    from .demo import DemoVerifier
    return DemoVerifier()
