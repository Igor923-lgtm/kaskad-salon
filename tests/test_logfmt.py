"""logfmt: гибрид — extra-поля → JSON (event/tenant), без них → старый plain-формат.

Must set env BEFORE importing api/config.
"""
import io
import json
import logging
import os
import re
import tempfile

os.environ.setdefault("CRM_SECRET", "test_secret_for_unit_tests")
os.environ.setdefault("CRM_PASSWORD", "test_crm_pass")
os.environ.setdefault("SALON_ID", "testsalon")
os.environ.setdefault("CRM_TOKEN_FIXED", "fixed_test_crm_token")
_tmp = tempfile.mkdtemp(prefix="kaskad_logfmt_test_")
os.environ.setdefault("DB_PATH", os.path.join(_tmp, "bot_cache.db"))

from logfmt import PLAIN_FORMAT, StructuredFormatter, log_event

_counter = {"n": 0}


def _capture(tenant="testsalon"):
    _counter["n"] += 1
    name = f"logfmt_probe_{_counter['n']}"
    buf = io.StringIO()
    lg = logging.getLogger(name)
    lg.handlers.clear()
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    h = logging.StreamHandler(buf)
    h.setFormatter(StructuredFormatter(tenant=tenant))
    lg.addHandler(h)
    return lg, buf


def test_extra_fields_become_json_with_event_and_tenant():
    lg, buf = _capture()
    log_event(lg, logging.WARNING, "auth_401", path="/api/x", method="GET")
    data = json.loads(buf.getvalue().strip())
    assert data["event"] == "auth_401"
    assert data["tenant"] == "testsalon"
    assert data["path"] == "/api/x"
    assert data["method"] == "GET"
    assert data["level"] == "WARNING"
    assert "auth_401" in data["msg"]  # человекочитаемая строка внутри JSON


def test_record_without_extra_keeps_old_format_exactly():
    lg, buf = _capture()
    lg.warning("plain text here")
    line = buf.getvalue().rstrip("\n")
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \[WARNING\] plain text here",
        line,
    )
    assert PLAIN_FORMAT == "%(asctime)s [%(levelname)s] %(message)s"


def test_unserializable_value_falls_back_without_crash():
    lg, buf = _capture()

    class Boom:
        def __str__(self):
            raise RuntimeError("nope")

    log_event(lg, logging.INFO, "weird", obj=Boom())  # не должно упасть
    out = buf.getvalue()
    assert out.strip()
    assert "weird" in out


def test_reserved_field_names_are_dropped_no_keyerror():
    lg, buf = _capture()
    # На Python ≥3.12 любой атрибут LogRecord в extra → KeyError в makeRecord
    log_event(lg, logging.INFO, "evt", name="evil", levelname="EVIL",
              message="boom", asctime="nope")
    data = json.loads(buf.getvalue().strip())
    assert data["event"] == "evt"
    assert data["logger"] == lg.name
    assert data["level"] == "INFO"
    for bad in ("name", "levelname", "message", "asctime"):
        assert bad not in data


def test_tenant_defaults_to_config_salon_id():
    import config
    _counter["n"] += 1
    buf = io.StringIO()
    lg = logging.getLogger(f"logfmt_probe_{_counter['n']}")
    lg.handlers.clear()
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    h = logging.StreamHandler(buf)
    h.setFormatter(StructuredFormatter())  # tenant берётся из config.SALON_ID
    lg.addHandler(h)
    log_event(lg, logging.INFO, "evt")
    data = json.loads(buf.getvalue().strip())
    assert data["tenant"] == config.SALON_ID


def test_api_logger_has_exactly_one_structured_handler():
    import api
    handlers = api.log.handlers
    assert len(handlers) == 1, f"ожидался ровно один handler, найдено: {handlers}"
    assert isinstance(handlers[0].formatter, StructuredFormatter)


def test_log_event_survives_fully_broken_field_name():
    lg, buf = _capture()
    log_event(lg, logging.INFO, "evt", **{"a b": "space in key"})  # не identifier
    # Логгер не упал; что именно записалось — формат на усмотрение фолбэка
    assert lg.handlers  # handler на месте
    log_event(lg, logging.INFO, "evt2")
    data = json.loads([l for l in buf.getvalue().splitlines() if l][-1])
    assert data["event"] == "evt2"
