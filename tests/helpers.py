from itertools import count

from app.email.models import IncomingEmail

_seq = count(1)


def make_email(**kw) -> IncomingEmail:
    n = next(_seq)
    data = dict(
        message_id=f"<msg-{n}@teste>",
        from_email="cliente@empresa.com",
        subject="Internet fora do ar",
        body="Estamos sem internet desde as 14h.",
    )
    data.update(kw)
    return IncomingEmail(**data)
