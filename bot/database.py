"""
MongoDB async database layer using Motor.

Singleton ``Database`` instance — initialised once in ``post_init``.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from bot.utils.helpers import utcnow

logger = logging.getLogger(__name__)


class Database:
    """Wraps a Motor client and exposes typed helpers for every collection."""

    def __init__(self, uri: str, db_name: str) -> None:
        self.client: AsyncIOMotorClient = AsyncIOMotorClient(
            uri, maxPoolSize=10, serverSelectionTimeoutMS=5000
        )
        self.db = self.client[db_name]

        # Collections
        self.users = self.db["users"]
        self.settings_col = self.db["settings"]
        self.rom_mappings = self.db["rom_mappings"]
        self.patch_jobs = self.db["patch_jobs"]
        self.cache_col = self.db["cache"]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def init_indexes(self) -> None:
        """Create indexes (idempotent)."""
        await self.users.create_index("user_id", unique=True)
        await self.cache_col.create_index("cache_key", unique=True)
        await self.rom_mappings.create_index("name", unique=True)
        await self.patch_jobs.create_index("user_id")
        await self.patch_jobs.create_index("status")
        logger.info("Database indexes ensured")

    def close(self) -> None:
        self.client.close()
        logger.info("Database connection closed")

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    async def upsert_user(self, user) -> None:
        """Insert or update a Telegram user record."""
        await self.users.update_one(
            {"user_id": user.id},
            {
                "$set": {
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "last_active": utcnow(),
                },
                "$setOnInsert": {
                    "user_id": user.id,
                    "joined_at": utcnow(),
                    "is_blocked": False,
                },
            },
            upsert=True,
        )

    async def mark_user_blocked(self, user_id: int) -> None:
        await self.users.update_one(
            {"user_id": user_id}, {"$set": {"is_blocked": True}}
        )

    async def unmark_user_blocked(self, user_id: int) -> None:
        await self.users.update_one(
            {"user_id": user_id}, {"$set": {"is_blocked": False}}
        )

    async def get_broadcast_users(self) -> list[dict]:
        """Return all non-blocked users."""
        cursor = self.users.find(
            {"is_blocked": {"$ne": True}}, {"user_id": 1, "_id": 0}
        )
        return await cursor.to_list(length=None)

    async def get_user_stats(self) -> dict:
        """Return aggregate user statistics."""
        now = utcnow()
        total = await self.users.count_documents({})
        blocked = await self.users.count_documents({"is_blocked": True})
        active_7d = await self.users.count_documents(
            {"last_active": {"$gte": now - timedelta(days=7)}}
        )
        recent_24h = await self.users.count_documents(
            {"last_active": {"$gte": now - timedelta(hours=24)}}
        )
        return {
            "total": total,
            "blocked": blocked,
            "active": total - blocked,
            "active_7d": active_7d,
            "recent_24h": recent_24h,
        }

    # ------------------------------------------------------------------
    # Settings (key-value store)
    # ------------------------------------------------------------------
    async def get_setting(self, key: str) -> Optional[Any]:
        doc = await self.settings_col.find_one({"key": key})
        return doc["value"] if doc else None

    async def set_setting(self, key: str, value: Any) -> None:
        await self.settings_col.update_one(
            {"key": key}, {"$set": {"key": key, "value": value}}, upsert=True
        )

    # ------------------------------------------------------------------
    # ROM mappings
    # ------------------------------------------------------------------
    async def get_rom_mappings(self) -> list[dict]:
        """Return all ROM mappings sorted by order."""
        cursor = self.rom_mappings.find().sort("order", 1)
        return await cursor.to_list(length=None)

    async def add_rom_mapping(
        self,
        name: str,
        file_id: str,
        file_unique_id: str,
        file_name: str,
    ) -> None:
        """Add or replace a ROM mapping."""
        count = await self.rom_mappings.count_documents({})
        await self.rom_mappings.update_one(
            {"name": name},
            {
                "$set": {
                    "name": name,
                    "file_id": file_id,
                    "file_unique_id": file_unique_id,
                    "file_name": file_name,
                    "added_at": utcnow(),
                },
                "$setOnInsert": {"order": count},
            },
            upsert=True,
        )

    async def remove_rom_mapping(self, name: str) -> bool:
        result = await self.rom_mappings.delete_one({"name": name})
        return result.deleted_count > 0

    async def get_rom_by_name(self, name: str) -> Optional[dict]:
        return await self.rom_mappings.find_one({"name": name})

    # ------------------------------------------------------------------
    # Cache (with in-progress markers)
    # ------------------------------------------------------------------
    async def find_cache(self, cache_key: str) -> Optional[dict]:
        """Return a completed cache entry, or None."""
        return await self.cache_col.find_one(
            {"cache_key": cache_key, "status": "completed"}
        )

    async def mark_cache_in_progress(self, cache_key: str, user_id: int) -> bool:
        """
        Set an in-progress marker.  Returns True if set successfully.
        Returns False if there is already an in-progress or completed entry.
        """
        try:
            await self.cache_col.update_one(
                {"cache_key": cache_key},
                {
                    "$setOnInsert": {
                        "cache_key": cache_key,
                        "status": "in_progress",
                        "user_id": user_id,
                        "started_at": utcnow(),
                    }
                },
                upsert=True,
            )
            # Check if we actually set it (not overwriting a completed entry)
            doc = await self.cache_col.find_one({"cache_key": cache_key})
            return doc is not None and doc.get("status") == "in_progress"
        except Exception:
            return False

    async def clear_cache_in_progress(self, cache_key: str) -> None:
        """Remove a failed in-progress marker."""
        await self.cache_col.delete_one(
            {"cache_key": cache_key, "status": "in_progress"}
        )

    async def store_cache(
        self,
        cache_key: str,
        output_file_id: str,
        output_message_id: int,
        patch_hash: str,
        rom_name: str,
        patch_type: str,
    ) -> None:
        """Store a completed cache entry (overwrites in-progress)."""
        await self.cache_col.update_one(
            {"cache_key": cache_key},
            {
                "$set": {
                    "cache_key": cache_key,
                    "status": "completed",
                    "output_file_id": output_file_id,
                    "output_message_id": output_message_id,
                    "patch_hash": patch_hash,
                    "rom_name": rom_name,
                    "patch_type": patch_type,
                    "created_at": utcnow(),
                }
            },
            upsert=True,
        )

    # ------------------------------------------------------------------
    # Patch jobs (history)
    # ------------------------------------------------------------------
    async def create_job(
        self,
        user_id: int,
        patch_hash: str,
        rom_name: str,
        patch_type: str,
    ) -> str:
        """Insert a new job record and return its _id as string."""
        result = await self.patch_jobs.insert_one(
            {
                "user_id": user_id,
                "patch_hash": patch_hash,
                "rom_name": rom_name,
                "patch_type": patch_type,
                "status": "queued",
                "created_at": utcnow(),
                "completed_at": None,
            }
        )
        return str(result.inserted_id)

    async def update_job_status(self, user_id: int, status: str) -> None:
        update: dict[str, Any] = {"$set": {"status": status}}
        if status in ("completed", "failed", "cancelled"):
            update["$set"]["completed_at"] = utcnow()
        await self.patch_jobs.update_one(
            {"user_id": user_id, "status": {"$in": ["queued", "processing",
                                                      "downloading_rom", "downloading_patch",
                                                      "patching", "uploading"]}},
            update,
        )

    async def get_active_job(self, user_id: int) -> Optional[dict]:
        return await self.patch_jobs.find_one(
            {"user_id": user_id, "status": {"$nin": ["completed", "failed", "cancelled"]}}
        )

    # ------------------------------------------------------------------
    # DB stats (admin)
    # ------------------------------------------------------------------
    async def get_db_stats(self) -> dict:
        """Return dbStats for the current database."""
        return await self.db.command("dbStats")
