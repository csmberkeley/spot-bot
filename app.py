import re, os
from utils import *

from flask import Flask, request

from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_bolt.oauth.oauth_settings import OAuthSettings

from apscheduler.schedulers.background import BackgroundScheduler

from dotenv import load_dotenv
from flask_pymongo import PyMongo

SPOT_WORDS = ["spot", "spotted", "spotting", "codespot", "codespotted", "codespotting"]
OAUTH_EXPIRATION_SECONDS = 600
EDIT_GRACE_PERIOD_SECONDS = 60
REFERENDUM_WINDOW_SECONDS = 86400 # change to 86400
REFERENDUM_EXPIRATION_SECONDS = 86400 # change to 86400
REFERENDUM_CHECK_SECONDS = 600 # Change to 600
BASE = "/spotbot"

SPOT_PATTERN = comp(r"(\b" + r"\b)|(\b".join(SPOT_WORDS) + r"\b)")
USER_PATTERN = re.compile(r"<@[a-zA-Z0-9]+>")

APPROVED_EMOJI = "white_check_mark"
DENIED_EMOJI = "x"

load_dotenv()

app = Flask("app")
app.config["MONGO_URI"] = os.environ.get("SPOTBOT_SECURE_LINK")
mongo = PyMongo(app)
db_client = mongo.cx
spot_data = SpotDatabase(db_client)
referendum_data = ReferendumDatabase(db_client, REFERENDUM_EXPIRATION_SECONDS)

# https://slack.dev/bolt-python/concepts#authenticating-oauth
oauth_settings = OAuthSettings(
    client_id=os.environ.get("SPOTBOT_CLIENT_ID"),
    client_secret=os.environ.get("SPOTBOT_CLIENT_SECRET"),
    scopes=[
        "channels:history",
        "chat:write",
        "files:read",
        "groups:history",
        "im:history",
        "mpim:read",
        "reactions:write",
        "users.profile:read",
        "reactions:read",
        "channels:read",
        "groups:read"
    ],
    installation_store=DatabaseInstallationStore(db_client),
    state_store=DatabaseOAuthStateStore(db_client, expiration_seconds=OAUTH_EXPIRATION_SECONDS),
    install_path=f"{BASE}/install/",
    redirect_uri_path=f"{BASE}/oauth_redirect/"
)

bolt_app = App(
    signing_secret=os.environ.get("SPOTBOT_SIGNING_SECRET"), 
    oauth_settings=oauth_settings
)

handler = SlackRequestHandler(bolt_app)

@app.route(f"{BASE}/install/")
def handle_install():
    return handler.handle(request)

@app.route(f"{BASE}/oauth_redirect/", methods=["GET"])
def handle_oauth():
    return handler.handle(request)

@app.route(f"{BASE}/events/", methods=["POST"])
def handle_events():
    print(f"Original request URL {request.base_url}")
    return handler.handle(request)

@bolt_app.event("member_joined_channel")
def joined_listener(event, body, say, client):
    if event["user"] != get_bot_user(client):
        return 
    with open("spotbot_intro.txt") as file:
        say(file.read())

    if "inviter" not in event:
        return 

    spot_data.configure_for_message(event, body)
    spot_data.set_manager(event["inviter"])
    spot_data.push_write()

@bolt_app.message(SPOT_PATTERN)
def spot_listener(event, body, say, client):
    if "files" not in event:
        return
    spot_data.configure_for_message(event, body)
    log_spot(event["channel"], event["user"], event["ts"], event["text"], event["files"], say, client)
    spot_data.push_write()

# Assumes matches SPOT_PATTERN and files are present. 
def log_spot(channel, user, ts, text, files, say, client, purged_recent=False):
    spotter = user
    found_spotted = USER_PATTERN.findall(text)
    found_spotted = list(set(found_spotted)) # remove duplicates
    found_spotted = [username[2:-1] for username in found_spotted]
    if spotter in found_spotted:
        found_spotted.remove(spotter)

    bot_user = get_bot_user(client)
    if bot_user in found_spotted:
        found_spotted.remove(bot_user)
    
    if not found_spotted:
        return 

    all_images = [image['url_private'] for image in files]

    spot_data.increment_spot(spotter, len(found_spotted))
    for spotted in found_spotted:
        spot_data.increment_caught(spotted, 1)
        spot_data.append_images(spotted, all_images)

    spot_data.add_message(message_id(ts), {
        "spotter": spotter,
        "spotted": found_spotted,
        "images": all_images,
        "ts": ts,
        "referendum": False
    })

    if not purged_recent: 
        recent = spot_data.get_recent()
        if recent == spotter: 
            say(f"<@{spotter}> is on fire 🥵")
            spot_data.set(RECENT, None)
        else: 
            spot_data.set(RECENT, spotter)
    else: 
        spot_data.set(RECENT, spotter)

    client.reactions_add(channel=channel, name=APPROVED_EMOJI, timestamp=ts)

@bolt_app.event({
    "type": "message",
    "subtype": "message_deleted"
})
def delete_listener(event, body):
    spot_data.configure_for_message(event, body)
    delete(message_id(event["deleted_ts"]))
    spot_data.push_write()

def delete(mid):
    message = spot_data.delete_message(mid)
    if not message:
        return
    spot_data.increment_spot(message["spotter"], -1 * len(message["spotted"]))
    for user in message["spotted"]:
        spot_data.increment_caught(user, -1)
        spot_data.update_value(f"{IMAGES}.{user}", "$pull", message["images"])

    spot_data.set(RECENT, None)

@bolt_app.event({
    "type": "message",
    "subtype": "message_changed"
})
def changed_listener(event, body, say, client):
    spot_data.configure_for_message(event, body)
    inner_event = event["message"]

    if "files" not in inner_event:
        return

    if not SPOT_PATTERN.search(inner_event["text"]):
        return

    if float(event["ts"]) - float(inner_event["ts"]) > EDIT_GRACE_PERIOD_SECONDS:
        # Only accept edits made soon after they are posted
        return 

    # If spots have been counted, they must be deleted and recounted.
    try:
        delete(message_id(inner_event["ts"]))
        client.reactions_remove(channel=event["channel"], name=APPROVED_EMOJI, timestamp=inner_event["ts"])
    except Exception as e:
        print("Encountered an exception while internally deleting a changed spot: ", e)

    log_spot(event["channel"], inner_event["user"], inner_event["ts"], 
        inner_event["text"], inner_event["files"], say, client, purged_recent=True)

    spot_data.push_write()

@bolt_app.message(comp("scoreboard|spotboard"))
def scoreboard_listener(event, say, body, client):
    try:
        words = event['text'].lower().split()
        n = int(words[words.index("spotboard") + 1])
    except:
        try:
            n = int(words[words.index("scoreboard") + 1])
        except:
            n = 5

    spot_data.configure_for_message(event, body)
    spots = spot_data.get({SPOT: True})
    if not spots:
        return 
    spots = spots[SPOT]
    scoreboard = sorted(spots.keys(), key=lambda p: spots[p], reverse=True)[:n]
    message = "Spotboard:\n" 
    for i, participant in enumerate(scoreboard):
        message += f"{i + 1}. {get_display_name(client, participant)} - {spots[participant]}\n" 
    say(message)

@bolt_app.message(comp(r"\bcaughtboard\b"))
def caughtboard_listener(event, say, body, client):
    try:
        words = event['text'].lower().split()
        n = int(words[words.index("caughtboard") + 1])
    except:
        n = 5
    spot_data.configure_for_message(event, body)
    caught = spot_data.get({CAUGHT: True})
    if not caught:
        return 
    caught = caught[CAUGHT]
    caughtboard = sorted(caught.keys(), key=lambda p: caught[p], reverse=True)[:n]
    message = "Caughtboard:\n" 
    for i, participant in enumerate(caughtboard):
        message += f"{i + 1}. {get_display_name(client, participant)} - {caught[participant]}\n" 
    say(message)

@bolt_app.message(comp(r"\bpics\b|\bphotos\b"))
def pics_listener(event, say, body, client):
    found_spotted = USER_PATTERN.search(event['text'])
    if not found_spotted:
        return
    spotted = found_spotted[0][2:-1]

    spot_data.configure_for_message(event, body)
    images = spot_data.get({IMAGES: True})
    if not images:
        return 
    images = images[IMAGES]

    message = f"Spots of {get_display_name(client, spotted)}:\n"
    for i, link in enumerate(images[spotted]):
        message += f"{i + 1}. {link}\n"
    say(message)

@bolt_app.message(comp(r"\breferendum\b"))
def referendum_listener(event, say, body, client):
    if "thread_ts" not in event:
        return

    if float(event["ts"]) - float(event["thread_ts"]) > REFERENDUM_WINDOW_SECONDS:
        # Only accept referendums that open within a certain window
        return 

    spot_data.configure_for_message(event, body)
    mid = message_id(event["thread_ts"])
    result = spot_data.set_referendum(mid, True)
    if result is not False:
        return 

    referendum_post = say(
        text = f"Good spot :+1: or bad spot :-1:? ", 
        thread_ts = event['thread_ts'],
        reply_broadcast = True
    )
    
    referendum_data.store_referendum({
        "spot_ts": event['thread_ts'], 
        "vote_ts": referendum_post["ts"],
        "channel_id": event["channel"],
        "team_id": body["team_id"],
        "loc_id": unique_location_identifier(event, body),
        "date": datetime.utcnow()
    })

    client.reactions_add(channel=referendum_post["channel"], name="+1", timestamp=referendum_post["ts"])
    client.reactions_add(channel=referendum_post["channel"], name="-1", timestamp=referendum_post["ts"])

@bolt_app.message(comp(r"\breset\b"))
def reset_listener(event, say, body, client):
    spot_data.configure_for_message(event, body)
    manager = spot_data.get_manager()
    if event["user"] != manager: 
        say("Only the person who invited Spot Bot to the channel can perform that action. ")
        return 

    if not re.search("reset yes i mean it really delete everything", event["text"], re.IGNORECASE):
        say("If you really want to delete every spot in this channel, please send \"reset yes i mean it really delete everything\". This action cannot be undone.")
        return
    
    say("Resetting the spot record. ")
    spot_data.drop_loc(manager)

def process_referenda():
    for referendum in referendum_data.expired_referenda(): 
        try: 
            process_referendum(referendum)
        except Exception as e:
            print("Encountered an exception while processing expired referenda: ", e)

def process_referendum(referendum):
    bot = bolt_app.installation_store.find_installation(team_id=referendum["team_id"], enterprise_id=None, user_id=None, is_enterprise_install=None)
    result = bolt_app.client.reactions_get(token=bot.bot_token, channel=referendum["channel_id"], timestamp=referendum["vote_ts"])
    yes_votes = set()
    no_votes = set()
    for reaction in result["message"]["reactions"]:
        names = reaction["name"].split("::")
        if names[0] == "+1" or names[0] == "thumbsup":
            ledger = yes_votes
        elif names[0] == "-1" or names[0] == "thumbsdown":
            ledger = no_votes
        else: 
            continue
        for user in reaction["users"]:
            ledger.add(user)

    if len(yes_votes) >= len(no_votes): 
        bolt_app.client.chat_postMessage(token=bot.bot_token, channel=referendum["channel_id"], thread_ts=referendum["spot_ts"], text="The spot is good! ")
        return 

    spot_data.configure_for_loc(referendum["loc_id"])
    delete(message_id(referendum["spot_ts"]))
    spot_data.push_write()
    bolt_app.client.reactions_remove(token=bot.bot_token, channel=referendum["channel_id"], name=APPROVED_EMOJI, timestamp=referendum["spot_ts"])
    bolt_app.client.reactions_add(token=bot.bot_token, channel=referendum["channel_id"], name=DENIED_EMOJI, timestamp=referendum["spot_ts"])
    bolt_app.client.chat_postMessage(token=bot.bot_token, channel=referendum["channel_id"], thread_ts=referendum["spot_ts"], text="The spot is bad. ")

scheduler = BackgroundScheduler()
scheduler.add_job(func=process_referenda, trigger="interval", seconds=REFERENDUM_CHECK_SECONDS)
scheduler.start()
process_referenda()

@bolt_app.event("file_shared")
@bolt_app.event("message")
def ignore(event):
    pass