from typing import Protocol


class Verifier(Protocol):
    """Contract between the website and your model.

    verify() receives JPEG/PNG bytes of one video frame and returns a dict:
      live        int 0-100   probability-like score that a live person is present
      label       str         REAL | BORDERLINE | FAKE | NO_FACE
      confidence  float 0-1
      face        int | None  number of faces found (None if unknown)
      b, m        numbers     light level / motion (demo engine only, else 0)
      engine      str         which implementation answered
    """

    def verify(self, image_bytes: bytes, session: str = "default") -> dict: ...
