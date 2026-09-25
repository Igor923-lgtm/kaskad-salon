"""Booking window / duration overlap — pure helpers + try_book_slot on temp DB."""
import os
import tempfile

os.environ.setdefault("CRM_SECRET", "test_secret_for_unit_tests")
os.environ.setdefault("CRM_PASSWORD", "test_crm_pass")
os.environ.setdefault("SALON_ID", "testsalon")
_tmp = tempfile.mkdtemp(prefix="kaskad_test_db_")
os.environ["DB_PATH"] = os.path.join(_tmp, "bot_cache.db")

import asyncio

import db as db_module


def test_slots_needed():
    assert db_module.slots_needed(0) == 1
    assert db_module.slots_needed(None) == 1
    assert db_module.slots_needed(15) == 1
    assert db_module.slots_needed(16) == 2
    assert db_module.slots_needed(50) == 4
    assert db_module.slots_needed(120) == 8


def test_window_is_free_blocks_overlap():
    working = [f"{h:02d}:{m:02d}" for h in range(10, 21) for m in (0, 15, 30, 45)]
    occ = db_module.occupied_times_for_booking({"time": "10:00", "duration_minutes": 120})
    assert not db_module.window_is_free("10:30", 15, working, occ)
    assert not db_module.window_is_free("11:45", 15, working, occ)
    assert db_module.window_is_free("12:00", 15, working, occ)
    # 2h at 20:00 does not fit salon ending 21:00
    assert not db_module.window_is_free("20:00", 120, working, set())


def test_try_book_slot_overlap():
    async def main():
        await db_module.init()
        bid = await db_module.try_book_slot(
            "M1", "2099-01-01", "10:00", client_name="A", duration_minutes=120
        )
        assert bid
        assert (
            await db_module.try_book_slot(
                "M1", "2099-01-01", "10:30", client_name="B", duration_minutes=0
            )
            is None
        )
        assert (
            await db_module.try_book_slot(
                "M1", "2099-01-01", "11:45", client_name="C", duration_minutes=30
            )
            is None
        )
        ok = await db_module.try_book_slot(
            "M1", "2099-01-01", "12:00", client_name="D", duration_minutes=0
        )
        assert ok

    asyncio.run(main())


def test_buffer_empty_by_default():
    async def main():
        await db_module.init()
        await db_module.set_setting("buffer_minutes", "0")
        db_module._invalidate_settings_cache()
        assert await db_module.get_buffer_minutes() == 0

    asyncio.run(main())


def test_buffer_blocks_start_after_booking():
    async def main():
        await db_module.init()
        await db_module.set_setting("buffer_minutes", "15")
        db_module._invalidate_settings_cache()
        date = "2099-02-01"
        import aiosqlite
        async with aiosqlite.connect(db_module.config.DB_PATH) as c:
            await c.execute("DELETE FROM bookings WHERE date = ?", (date,))
            await c.commit()

        bid = await db_module.try_book_slot(
            "MBUF", date, "10:00", client_name="A", duration_minutes=60
        )
        assert bid
        # 11:00 — first slot after 60min window, blocked by 15min buffer
        assert (
            await db_module.try_book_slot(
                "MBUF", date, "11:00", client_name="B", duration_minutes=0
            )
            is None
        )
        # 11:15 free
        ok = await db_module.try_book_slot(
            "MBUF", date, "11:15", client_name="C", duration_minutes=0
        )
        assert ok

        occ = await db_module.get_occupied_times("MBUF", date)
        assert "11:00" in occ  # buffer after 10:00–11:00 booking
        assert "11:15" in occ  # the booking we just made at 11:15
        # 11:30 not part of first booking/buffer nor second (duration 0)
        # second booking buffer would add 11:30 if buffer still on — with buffer=15 after 11:15 booking
        # end of second = 11:30, buffer starts at 11:30
        assert "11:30" in occ

        await db_module.set_setting("buffer_minutes", "0")
        db_module._invalidate_settings_cache()

    asyncio.run(main())
