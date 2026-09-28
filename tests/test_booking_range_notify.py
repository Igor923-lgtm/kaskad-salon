"""Диапазоны напоминаний: один бронь-диапазон → одно сообщение, без спама."""
import os
import tempfile

os.environ.setdefault("CRM_SECRET", "test_secret_for_unit_tests")
os.environ.setdefault("CRM_PASSWORD", "test_crm_pass")
os.environ.setdefault("SALON_ID", "testsalon")
_tmp = tempfile.mkdtemp(prefix="kaskad_test_db_")
os.environ["DB_PATH"] = os.path.join(_tmp, "bot_cache.db")

import asyncio

import db as db_module


def test_expand_booking_ranges_returns_full_range():
    """Один выбранный слот тянет весь диапазон 18:00–20:00 (8 слотов)."""

    async def main():
        await db_module.init()
        date = "2099-03-01"
        # 8 слотов диапазона одного клиента
        count = await db_module.book_range(
            master_name="Пространство",
            date=date,
            start_time="18:00",
            end_time="20:00",
            client_name="Клиент",
            telegram_id=777001,
            service_name="Рабочее место",
        )
        assert count == 8
        # Отдельная бронь того же дня/клиента — не должна слипнуться с диапазоном
        other = await db_module.try_book_slot(
            master_name="Пространство",
            date=date,
            time="21:00",
            client_name="Клиент",
            telegram_id=777001,
            service_name="Рабочее место",
        )
        assert other

        import aiosqlite
        async with aiosqlite.connect(db_module.config.DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            cur = await c.execute(
                "SELECT * FROM bookings WHERE date = ? AND time = '18:00' AND telegram_id = 777001",
                (date,),
            )
            first = dict(await cur.fetchone())

        # Как окно напоминания: выбран только первый слот
        expanded = await db_module.expand_booking_ranges([first])
        times = sorted(r["time"] for r in expanded)
        assert times == [f"18:{m:02d}" for m in (0, 15, 30, 45)] + [f"19:{m:02d}" for m in (0, 15, 30, 45)]

        # Группировка даёт ровно одну группу на диапазон + отдельную на 21:00
        groups = db_module.group_consecutive_slots(expanded)
        assert len(groups) == 1
        assert groups[0]["start_time"] == "18:00"
        assert groups[0]["end_time"] == "20:00"
        assert len(groups[0]["ids"]) == 8

        # Несвязанная бронь 21:00 не попала в expansion
        assert all(r["time"] != "21:00" for r in expanded)

    asyncio.run(main())


def test_expand_booking_ranges_empty():
    assert asyncio.run(db_module.expand_booking_ranges([])) == []
