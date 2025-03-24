from slack_sdk.oauth.installation_store import InstallationStore, Installation, Bot
from slack_sdk.oauth.state_store import OAuthStateStore
from typing import Optional
import pymongo, string, random, re
from pymongo.collection import ReturnDocument
from datetime import datetime, timedelta
import hashlib


CONFIG_DATABASE_NAME = "spot-bot-config"
INSTALL_COLLECTION_NAME = "installations"
BOT_COLLECTION_NAME = "bots"
STATE_COLLECTION_NAME = "oauth-state"

MAIN_DATABASE_NAME = "spot-bot"
MAIN_COLLECTION_NAME = "spot-bot-main"
CAUGHT = "caught"
SPOT = "spot"
RECENT = "recent"
MESSAGES = "messages"
IMAGES = "images"
MANAGER = "manager"
TEAM_ID = "team_id"
CHANNEL_ID = "channel_id"

REFERENDUM_COLLECTION_NAME = "referenda"

def remove_nones(dictionary):
    out = {}
    for key in dictionary:
        if dictionary[key] is not None:
            out[key] = dictionary[key]
    return out

class DatabaseInstallationStore(InstallationStore):
    def __init__(self, client):
        db = client.get_database(CONFIG_DATABASE_NAME)
        self.install_collection = db.get_collection(INSTALL_COLLECTION_NAME)
        self.bot_collection = db.get_collection(BOT_COLLECTION_NAME)

    def save(self, installation: Installation):
        print("Saving installation to installation store. ")
        self.install_collection.insert_one(installation.to_dict())

    def save_bot(self, bot: Bot):
        print("Saving bot to installation store. ")
        self.bot_collection.insert_one(bot.to_dict())

    def find_bot(self, *, enterprise_id: Optional[str], team_id: Optional[str], is_enterprise_install: Optional[bool] = False) -> Optional[Bot]:
        print("Finding in bot store. ")
        query = dict(
            enterprise_id=enterprise_id,
            team_id=team_id,
            is_enterprise_install=is_enterprise_install
        )
        query = remove_nones(query)
        
        result = self.bot_collection.find_one(query, projection={"_id": False}, sort=[("installed_at", pymongo.DESCENDING)])
        if result:
            return Bot(**result)
        return None

    def find_installation(self, *, enterprise_id: Optional[str], team_id: Optional[str], user_id: Optional[str] = None, is_enterprise_install: Optional[bool] = False):
        print("Finding in installation store. ")
        query = dict(
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=user_id,
            is_enterprise_install=is_enterprise_install
        )
        query = remove_nones(query)
        
        result = self.install_collection.find_one(query, projection={"_id": False}, sort=[("installed_at", pymongo.DESCENDING)])
        if result:
            return Installation(**result)
        query.pop("user_id", None)
        result = self.install_collection.find_one(query, projection={"_id": False}, sort=[("installed_at", pymongo.DESCENDING)])
        if result:
            return Installation(**result)
        return None

    def delete_installation(self, *, enterprise_id: Optional[str], team_id: Optional[str], user_id: Optional[str] = None):
        print("Deleting installation.")
        query = dict(
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=user_id,
        )
        query = remove_nones(query)
        self.install_collection.delete_one(query)

    def delete_bot(self, *, enterprise_id: Optional[str], team_id: Optional[str]) -> None:
        print("Deleting bot.")
        query = dict(
            enterprise_id=enterprise_id,
            team_id=team_id,
        )
        query = remove_nones(query)
        self.bot_collection.delete_one(query)

class DatabaseOAuthStateStore(OAuthStateStore):
    def __init__(self, client, expiration_seconds):
        db = client.get_database(CONFIG_DATABASE_NAME)
        self.collection = db.get_collection(STATE_COLLECTION_NAME)
        self.expiration_seconds = expiration_seconds

    def issue(self):
        print("Issuing OAuth state. ")
        rand = random.SystemRandom()
        alphabet = string.ascii_letters + string.digits + "-_"
        state = "".join([rand.choice(alphabet) for _ in range(20)])
        self.collection.insert_one({"data": state, "date": datetime.utcnow()})
        return state

    def consume(self, state: str):
        print("Consuming OAuth state. ")
        self.collection.delete_many({"date" : {"$lt" : datetime.utcnow() - timedelta(seconds=self.expiration_seconds)} })
        return bool(self.collection.find_one_and_delete({"data": state}))

def unique_location_identifier(event, body):
    return hashlib.sha256(bytes(event["channel"] + body["team_id"], encoding="utf-8")).hexdigest()

class SpotDatabase():
    def __init__(self, client):
        db = client.get_database(MAIN_DATABASE_NAME)
        self.collection = db.get_collection(MAIN_COLLECTION_NAME)
        self.operations = []

    def configure_for_message(self, event, body):
        self.loc_id = unique_location_identifier(event, body)

    def configure_for_loc(self, loc_id):
        self.loc_id = loc_id

    def get(self, projection):
        return self.collection.find_one(filter={"loc_id": self.loc_id}, 
            projection=projection)

    def get_recent(self):
        result = self.get({RECENT: True, "_id": False})
        if not result or RECENT not in result:
            return []
        return result[RECENT]

    def get_manager(self):
        result = self.get({MANAGER: True})
        if not result or MANAGER not in result: 
            return 
        return result[MANAGER]
    
    def get_team_id(self):
        result = self.get({TEAM_ID: True})
        if not result or TEAM_ID not in result: 
            return 
        return result[TEAM_ID]
    
    def get_channel_id(self):
        result = self.get({CHANNEL_ID: True})
        if not result or CHANNEL_ID not in result: 
            return 
        return result[CHANNEL_ID]

    def drop_loc(self, manager):
        return self.collection.replace_one(
            filter={"loc_id": self.loc_id},
            replacement={
                "loc_id": self.loc_id, 
                MANAGER: manager
            })

    def delete_message(self, message_id):
        result = self.collection.find_one_and_update(
            filter={"loc_id": self.loc_id},
            update={"$unset": {f"{MESSAGES}.{message_id}": ""}}, 
            projection={f"{MESSAGES}.{message_id}": True},
            return_document=ReturnDocument.BEFORE
        )

        if result and "messages" in result and message_id in result["messages"]:
            print(result)
            return result["messages"][message_id]

    def set_referendum(self, mid, value):
        result = self.collection.find_one_and_update(
            filter={"loc_id": self.loc_id}, 
            update={"$set": 
                {f"{MESSAGES}.{mid}.referendum": value}
            },
            projection={f"{MESSAGES}.{mid}.referendum": True},
            upsert=True        
        )

        if not (result and MESSAGES in result and mid in result[MESSAGES]):
            return None

        return result[MESSAGES][mid]["referendum"]

    #=================================

    def plan_write(self, operation):
        self.operations.append(operation)

    def update_value(self, path, operation, argument):
        self.plan_write(pymongo.UpdateOne(
            filter={"loc_id": self.loc_id}, 
            update={operation: 
                {path: argument}
            },
            upsert=True        
        ))

    def increment(self, path, amount):
        self.update_value(path, "$inc", amount)

    def increment_spot(self, username, amount):
        self.increment(f"{SPOT}.{username}", amount)

    def increment_caught(self, username, amount):
        self.increment(f"{CAUGHT}.{username}", amount)

    def append(self, path, lst): 
        self.update_value(path, "$push", lst)

    def append_images(self, username, images):
        self.append(f"{IMAGES}.{username}", images)

    def set(self, path, attribute):
        self.update_value(path, "$set", attribute)

    def unset(self, path):
        self.update_value(path, "$unset", "")

    def add_message(self, message_id, message):
        self.set(f"{MESSAGES}.{message_id}", message)

    def set_manager(self, user): 
        self.set(f"{MANAGER}", user)

    def set_team_id(self, team_id): 
        self.set(f"{TEAM_ID}", team_id)

    def set_channel_id(self, channel_id): 
        self.set(f"{CHANNEL_ID}", channel_id)

    def pop(self, path, from_front: bool):
        self.update_value(path, "$pop", -1 if from_front else 1)

    def push_write(self):
        self.collection.bulk_write(self.operations)
        self.operations.clear()

class ReferendumDatabase():

    def __init__(self, client, expiration_seconds):
        db = client.get_database(MAIN_DATABASE_NAME)
        self.collection = db.get_collection(REFERENDUM_COLLECTION_NAME)
        self.expiration_seconds = expiration_seconds

    def store_referendum(self, referendum):
        self.collection.insert_one(referendum)

    def expired_referenda(self):
        expired = self.collection.find({"date" : {"$lt" : datetime.utcnow() - timedelta(seconds=self.expiration_seconds)} })
        referenda = []
        ids = []
        for referendum in expired: 
            referenda.append(referendum)
            ids.append(referendum["_id"])

        self.collection.delete_many({ "_id" : { "$in": ids } })
        return referenda

def message_id(timestamp):
    return hashlib.sha256(bytes(timestamp, encoding="utf-8")).hexdigest()

def comp(pattern):
    return re.compile(pattern, re.IGNORECASE)

def get_display_name(client, user):
    try:
        profile = client.users_profile_get(user=user)['profile']
        return profile['display_name'] or profile['real_name']
    except Exception as e:
        print("couldn't find: ", user, e)

def get_bot_user(client):
    bot_info = client.auth_test()
    bot_user = bot_info["user_id"]
    return bot_user