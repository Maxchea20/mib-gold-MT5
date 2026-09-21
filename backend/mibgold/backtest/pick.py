import os
from ..scalp import Engine, ScalpConfig, ContEngine
from ..scalp.hunt_h2 import HuntEngine
from ..scalp.cfast_v2_h2 import CFastV2Hunt


def make_engine(book: str = "scalp_v1"):
    b = (book or "").strip().lower() or "scalp_v1"
    env = (os.environ.get("MIBGOLD_LAB_BOOK") or "").strip().lower()
    if b in ("scalp_v1", "v1", "") and env:
        b = env
    if env and b in ("hunt_h2", "cont_h1", "scalp_v1") and env.startswith("cfast"):
        b = env
    if b in ("cfast_v2_h2", "cfast-v2-h2", "v2h2", "cfast_v2"):
        return CFastV2Hunt(), "C-FAST V2 + H2"
    if b in ("cont_h1", "cont-h1", "conth1"):
        return ContEngine(), "CONT-H1"
    if b in ("hunt_h2", "hunt-h2", "hunth2", "hunt"):
        return HuntEngine(), "HUNT H2"
    return Engine(ScalpConfig()), "Scalp V1 research"
