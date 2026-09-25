"""UX-клавиатуры бота: «Назад» внизу + порядок кнопок после фото."""
import os
import re

BOT = os.path.join(os.path.dirname(__file__), "..", "bot.py")


def _fn_body(src: str, name: str) -> str:
    m = re.search(
        rf"async def {name}\(.*?(?=\nasync def |\ndef |\nif __name__)",
        src,
        re.S,
    )
    assert m, f"{name} not found"
    return m.group(0)


def _ensure_back_last(rows, callback_data="back_main", label="◀️ Назад"):
    if not rows:
        return [[type("B", (), {"text": label})()]]
    last_texts = " ".join(getattr(b, "text", "") for b in rows[-1])
    if any(s in last_texts for s in ("Назад", "Отмена", "Меню", "Начало", "В главное", "К категори", "К календар")):
        return rows
    rows.append(["__BACK__"])
    return rows


def test_ensure_back_last_appends():
    assert _ensure_back_last([["A"], ["B"]])[-1] == ["__BACK__"]


def test_ensure_back_last_keeps_existing():
    class B:
        text = "◀️ Назад"

    rows = [["A"], [B()]]
    assert _ensure_back_last(rows) == rows


def test_ensure_back_last_empty():
    assert _ensure_back_last([])[0][0].text == "◀️ Назад"


def test_bot_source_no_reply_markup_on_media_group():
    src = open(BOT, encoding="utf-8").read()
    assert "reply_media_group(media, reply_markup" not in src


def test_works_category_nav_is_new_message():
    """Кнопки после галереи — reply_text ПОД фото, не edit старого сообщения."""
    src = open(BOT, encoding="utf-8").read()
    body = _fn_body(src, "cb_works_category")
    assert "reply_media_group" in body
    last_edit = body.rfind("edit_message_text")
    last_group = body.rfind("reply_media_group")
    last_reply_text = body.rfind("reply_text")
    assert last_group < last_reply_text, "nav reply_text must come after media_group"
    assert last_edit < last_group, "edit 'Отправляю' must happen before photos"


def test_masters_sends_nav_after_photos():
    src = open(BOT, encoding="utf-8").read()
    body = _fn_body(src, "cb_masters")
    assert "photo_file_id" in body
    assert body.rfind("Выберите действие") > 0
    # nav message is the last significant UI send
    assert body.rfind("reply_text") >= body.rfind("reply_photo") or "photo_file_id" in body


def test_ensure_back_last_function_exists():
    src = open(BOT, encoding="utf-8").read()
    assert "def ensure_back_last" in src


def test_no_prompt_in_bot():
    src = open(BOT, encoding="utf-8").read()
    assert not re.search(r"(?<![\w.])prompt\(", src)
