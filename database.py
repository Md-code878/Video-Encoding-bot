from motor.motor_asyncio import AsyncIOMotorClient
from config import Config


class Database:
    def __init__(self):
        self._client = AsyncIOMotorClient(Config.MONGO_URI)
        self._db = self._client[Config.DB_NAME]
        self._users = self._db["users"]
        self._tasks = self._db["tasks"]
        self._settings = self._db["settings"]

    # ── User Management ──────────────────────────────────────────────

    async def add_user(self, user_id: int, username: str = ""):
        await self._users.update_one(
            {"user_id": user_id},
            {
                "$set": {"username": username},
                "$setOnInsert": {
                    "user_id": user_id,
                    "is_banned": False,
                    "default_codec": "hevc",
                    "default_resolution": None,
                    "tasks_completed": 0,
                },
            },
            upsert=True,
        )

    async def get_user(self, user_id: int):
        return await self._users.find_one({"user_id": user_id})

    async def get_all_users(self):
        return await self._users.find().to_list(None)

    async def total_users(self) -> int:
        return await self._users.count_documents({})

    async def ban_user(self, user_id: int):
        await self._users.update_one(
            {"user_id": user_id}, {"$set": {"is_banned": True}}
        )

    async def unban_user(self, user_id: int):
        await self._users.update_one(
            {"user_id": user_id}, {"$set": {"is_banned": False}}
        )

    async def is_banned(self, user_id: int) -> bool:
        user = await self._users.find_one({"user_id": user_id})
        return user.get("is_banned", False) if user else False

    async def set_user_codec(self, user_id: int, codec: str):
        await self._users.update_one(
            {"user_id": user_id}, {"$set": {"default_codec": codec}}
        )

    async def set_user_resolution(self, user_id: int, resolution: str | None):
        await self._users.update_one(
            {"user_id": user_id}, {"$set": {"default_resolution": resolution}}
        )

    async def increment_tasks(self, user_id: int):
        await self._users.update_one(
            {"user_id": user_id}, {"$inc": {"tasks_completed": 1}}
        )

    # ── Task Tracking ────────────────────────────────────────────────

    async def add_task(self, task_data: dict):
        return await self._tasks.insert_one(task_data)

    async def get_active_tasks(self):
        return await self._tasks.find({"status": "processing"}).to_list(None)

    async def update_task(self, task_id, update: dict):
        await self._tasks.update_one({"_id": task_id}, {"$set": update})

    async def total_tasks(self) -> int:
        return await self._tasks.count_documents({})

    # ── Global Settings ──────────────────────────────────────────────

    async def get_setting(self, key: str, default=None):
        doc = await self._settings.find_one({"key": key})
        return doc["value"] if doc else default

    async def set_setting(self, key: str, value):
        await self._settings.update_one(
            {"key": key}, {"$set": {"value": value}}, upsert=True
        )


db = Database()
