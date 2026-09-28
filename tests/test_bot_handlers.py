"""Регистрация callback-хендлеров: меню работает из любого состояния,
несовпавшие callback'и никогда не оставляют спиннер висеть."""
import os
import tempfile

os.environ.setdefault("CRM_SECRET", "test_secret_for_unit_tests")
os.environ.setdefault("CRM_PASSWORD", "test_crm_pass")
os.environ.setdefault("SALON_ID", "testsalon")
_tmp = tempfile.mkdtemp(prefix="kaskad_test_db_")
os.environ["DB_PATH"] = os.path.join(_tmp, "bot_cache.db")
os.environ.setdefault(
    "BOT_TOKEN", "123456789:AAFakeTokenForUnitTestsOnly_abcdefghijklmnop"
)

import pytest
from telegram.ext import ConversationHandler

import bot


@pytest.fixture(scope="module")
def app():
    return bot.build_application()


@pytest.fixture(scope="module")
def conv(app):
    return next(h for h in app.handlers[0] if isinstance(h, ConversationHandler))


def _patterns(handlers):
    return [h.pattern.pattern for h in handlers if getattr(h, "pattern", None)]


def test_nav_buttons_are_entry_points(conv):
    """Главное меню должно работать из любого состояния и после таймаута."""
    patterns = _patterns(conv.entry_points)
    for expected in (
        "^menu_services$",
        "^menu_masters$",
        "^menu_works$",
        "^menu_my_bookings$",
        "^menu_edit_booking$",
        "^menu_history$",
        "^menu_discount$",
        "^menu_birthday$",
        "^menu_location$",
        "^menu_waitlist$",
        "^menu_book$",
        "^menu_contact$",
        "^coworking$",
        "^back_main$",
        "^consultation$",
    ):
        assert expected in patterns, f"entry point {expected} missing"


def test_every_state_has_back(conv):
    """Из любого состояния должен вести путь назад в меню."""
    missing = [state for state, hs in conv.states.items() if "^back_main$" not in _patterns(hs)]
    assert not missing, f"states without back_main: {missing}"


def test_coworking_date_state_has_cal_back(conv):
    """Экран «Нет свободного времени» показывает cow_cal_back_."""
    patterns = _patterns(conv.states[bot.COWORKING_SELECT_DATE])
    assert "^cow_cal_back_" in patterns


def test_catch_all_is_last_in_group1(app):
    """Последний handler group=1 — тихая страховка, гасящая спиннер (state=None)."""
    group1 = app.handlers[1]
    assert group1, "group 1 is empty"
    catch_all = group1[-1]
    assert catch_all.pattern.pattern == ".*"
    # consultation больше не дублируется вне ConversationHandler
    patterns = _patterns(group1)
    assert "^consultation$" not in patterns


def test_conversation_fallback_answers_unmatched_callbacks(conv):
    """В активном состоянии несматченный callback получает alert, а не спиннер."""
    assert ".*" in _patterns(conv.fallbacks)
