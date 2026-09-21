import os
from ..scalp import Engine, ScalpConfig, ContEngine


def make_engine(book: str = "scalp_v1"):
    b = (book or "").strip().lower() or "scalp_v1"
    env = (os.environ.get("MIBGOLD_LAB_BOOK") or "").strip().lower()
    if b in ("scalp_v1", "v1", "") and env:
        b = env
    if b in ("cont_h1", "cont-h1", "conth1"):
        return ContEngine(), "CONT-H1"
    return Engine(ScalpConfig()), "Scalp V1 research"
