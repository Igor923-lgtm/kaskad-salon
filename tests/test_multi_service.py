"""Multi-service booking: Σ duration occupies one window."""
import os
import tempfile

os.environ.setdefault("CRM_SECRET", "test_secret_for_unit_tests")
os.environ.setdefault("CRM_PASSWORD", "test_crm_pass")
os.environ.setdefault("SALON_ID", "testsalon")
_tmp = tempfile.mkdtemp(prefix="kaskad_test_multi_")
os.environ["DB_PATH"] = os.path.join(_tmp, "bot_cache.db")

import asyncio

import db as db_module


def test_multi_services_sum_duration():
    async def main():
        await db_module.init()
        # seed category + two services
        cat = await db_module.add_category("MultiTest")
        s1 = await db_module.add_service("MultiTest", "", cat, "SvcA", "10", duration_minutes=60)
        s2 = await db_module.add_service("MultiTest", "", cat, "SvcB", "20", duration_minutes=30)
        svcs = await db_module.resolve_services_by_ids([s1, s2])
        assert len(svcs) == 2
        total = sum(db_module.slots_needed(s.get("duration_minutes")) * 15 for s in svcs)
        assert total == 90

        # occupy window as create_booking would
        bid = await db_module.try_book_slot(
            "MMULTI", "2099-04-01", "10:00",
            client_name="M", duration_minutes=total,
            service_name="SvcA + SvcB",
        )
        assert bid
        await db_module.set_booking_services(bid, [
            {"service_id": s1, "name": "SvcA", "price": "10", "duration_minutes": 60},
            {"service_id": s2, "name": "SvcB", "price": "20", "duration_minutes": 30},
        ])
        rows = await db_module.get_booking_services(bid)
        assert len(rows) == 2

        # 11:00 blocked (90 min from 10:00 → ends 11:30)
        assert (
            await db_module.try_book_slot(
                "MMULTI", "2099-04-01", "11:00", client_name="X", duration_minutes=0
            )
            is None
        )
        # 11:30 free (buffer 0)
        assert await db_module.try_book_slot(
            "MMULTI", "2099-04-01", "11:30", client_name="Y", duration_minutes=0
        )

        # cleanup join on delete path
        async with __import__("aiosqlite").connect(db_module.config.DB_PATH) as c:
            await c.execute("DELETE FROM bookings WHERE id = ?", (bid,))
            await c.execute("DELETE FROM booking_services WHERE booking_id = ?", (bid,))
            await c.commit()
        assert await db_module.get_booking_services(bid) == []

    asyncio.run(main())
