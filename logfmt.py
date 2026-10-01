"""Гибридное структурированное логирование (общее для api и bot).

Обычные записи печатаются ровно в старом формате; записи с extra-полями
(см. log_event) — одной JSON-строкой с event/tenant. Сломанный логгер
не должен ронять запрос: format() и log_event защищены фолбэками.
"""
import json
import logging

PLAIN_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

# Все атрибуты, которые LogRecord создаёт сам. extra с любым из них
# кидает KeyError в makeRecord (Python ≥3.12) — отбрасываем заранее.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime"}


class StructuredFormatter(logging.Formatter):
    """Есть extra-поля → JSON (ts/level/logger/msg/tenant + поля);
    нет → старый plain-формат, байт-в-байт."""

    def __init__(self, tenant: str | None = None):
        super().__init__(PLAIN_FORMAT)
        if tenant is None:
            try:
                import config
                tenant = config.SALON_ID
            except Exception:
                tenant = ""
        self._tenant = tenant

    def format(self, record: logging.LogRecord) -> str:
        try:
            extra = {
                k: v for k, v in record.__dict__.items()
                if k not in _RESERVED and not str(k).startswith("_")
            }
            if not extra:
                return super().format(record)
            payload = {
                "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
                **extra,
                "tenant": self._tenant,
            }
            out = json.dumps(payload, ensure_ascii=False, default=str)
            if record.exc_info and record.exc_info[0] is not None:
                out += "\n" + self.formatException(record.exc_info)
            return out
        except Exception:
            try:
                return super().format(record)
            except Exception:
                return f"{record.levelname}: {record.getMessage()}"


def log_event(log: logging.Logger, level: int, event: str, **fields) -> None:
    """Событийный лог: event + произвольные поля → JSON через StructuredFormatter."""
    clean = {
        k: v for k, v in fields.items()
        if k not in _RESERVED and k != "tenant" and not str(k).startswith("_")
    }
    try:
        rendered = " ".join([str(event)] + [f"{k}={v}" for k, v in clean.items()])
    except Exception:
        rendered = str(event)
    payload = dict(clean, event=str(event))
    try:
        log.log(level, rendered, extra=payload)
    except Exception:
        # Последний рубеж: сломанное имя/значение поля не должно ронять запрос
        try:
            log.log(level, str(event), extra={"event": str(event)})
        except Exception:
            pass
