"""Dump active PG sessions + locks holding critical tables (debug helper)."""

import asyncio

from sqlalchemy import text

from app.db.base import engine


async def main() -> None:
    async with engine.connect() as c:
        print("=== pg_stat_activity (non-idle) ===")
        r = await c.execute(
            text(
                "SELECT pid, state, wait_event_type, wait_event, age(now(),xact_start) AS xact_age, substr(query,1,200) "
                "FROM pg_stat_activity WHERE state <> 'idle' AND pid <> pg_backend_pid()"
            )
        )
        for row in r.fetchall():
            print(row)
        print("=== blocking locks ===")
        r = await c.execute(
            text(
                "SELECT blocked_locks.pid AS blocked_pid, blocking_locks.pid AS blocking_pid, "
                "substr(blocked_activity.query,1,120) AS blocked_query, substr(blocking_activity.query,1,120) AS blocking_query "
                "FROM pg_catalog.pg_locks blocked_locks "
                "JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid "
                "JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype "
                "AND blocking_locks.DATABASE IS NOT DISTINCT FROM blocked_locks.DATABASE "
                "AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation "
                "AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page "
                "AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple "
                "AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid "
                "AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid "
                "AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid "
                "AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid "
                "AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid "
                "AND blocking_locks.pid <> blocked_locks.pid "
                "JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid "
                "WHERE NOT blocked_locks.granted"
            )
        )
        for row in r.fetchall():
            print(row)


if __name__ == "__main__":
    asyncio.run(main())
