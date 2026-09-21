from ..scalp import Engine, ScalpConfig, ContEngine


def make_engine(book: str = "scalp_v1"):
    b = (book or "scalp_v1").lower()
    if b in ("cont_h1", "cont-h1", "conth1"):
        return ContEngine(), "CONT-H1"
    return Engine(ScalpConfig()), "Scalp V1 research"
