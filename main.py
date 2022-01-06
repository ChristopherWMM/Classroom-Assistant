import os
import re
import urllib
import hashlib
import logging

from slack_bolt import App, BoltResponse

from flask import Flask, request, make_response
from slack_bolt.adapter.flask import SlackRequestHandler

from slack_bolt.oauth.oauth_settings import OAuthSettings
from slack_bolt.oauth.callback_options import CallbackOptions, SuccessArgs, FailureArgs

from slack_sdk.oauth.installation_store.sqlalchemy import SQLAlchemyInstallationStore
from slack_sdk.oauth.state_store.sqlalchemy import SQLAlchemyOAuthStateStore

import sqlalchemy

from slack_utils import app_constants
from dialogflow_utils import knowledge_base_utils, document_utils, intent_utils

from dotenv import load_dotenv

load_dotenv()

# Globals

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

project_id = os.environ.get("DIALOGFLOW_PROJECT_ID")

# Cached changes for display updates.
uploading_files = dict()
uploading_entries = dict()

removing_files = dict()
removing_entries = dict()

# OAuth

def success(args: SuccessArgs) -> BoltResponse:
	team_id = args.installation.team_id

	# Check for an existing knowledge base and create one if need be.
	existing_knowledge_base = knowledge_base_utils.get_knowledge_base_by_name(
		project_id=project_id,
		knowledge_base_name=team_id
	)

	if existing_knowledge_base is None:
		knowledge_base_utils.create_knowledge_base(
			project_id=project_id,
			display_name=team_id
		)

	return args.default.success(args)

def failure(args: FailureArgs) -> BoltResponse:
	return BoltResponse(status=args.suggested_status_code, body=args.reason)

# App
database_url = os.getenv("DATABASE_URL")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

engine = sqlalchemy.create_engine(database_url)
installation_store = SQLAlchemyInstallationStore(
    client_id=os.environ.get("SLACK_CLIENT_ID"),
    engine=engine,
    logger=logger,
)

oauth_state_store = SQLAlchemyOAuthStateStore(
    expiration_seconds=120,
    engine=engine,
    logger=logger,
)

try:
    engine.execute("select count(*) from slack_bots")
except Exception as e:
    installation_store.metadata.create_all(engine)
    oauth_state_store.metadata.create_all(engine)

app = App(
	signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
	installation_store=installation_store,
	oauth_settings=OAuthSettings(
		client_id=os.environ.get("SLACK_CLIENT_ID"),
		client_secret=os.environ.get("SLACK_CLIENT_SECRET"),
		scopes=[
			"app_mentions:read",
			"users:read",
			"reactions:read",
			"chat:write",
			"im:write",
			"reactions:write",
			"channels:history",
			"groups:history",
			"im:history",
			"mpim:history",
			"commands"],
		user_scopes=[],
		redirect_uri=None,
		install_path="/slack/install",
		redirect_uri_path="/slack/oauth_redirect",
		state_store=oauth_state_store,
		callback_options=CallbackOptions(success=success, failure=failure),
	)
)

# Flask

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@flask_app.route("/")
def homepage():
	return "<h1>Online! 🤖</h1>"

from expiringdict import ExpiringDict
event_cache = ExpiringDict(max_len=100, max_age_seconds=120)

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
	if not request.is_json:
		return handler.handle(request)

	event_id = request.get_json()["event_id"]
	if event_id not in event_cache:
		event_cache[event_id] = request
		response = handler.handle(request)
	else:
		response = make_response("", 429)
		response.headers.add_header("X-Slack-No-Retry", 1)
	return response

@flask_app.route("/slack/install", methods=["GET"])
def install():
	return handler.handle(request)

@flask_app.route("/slack/oauth_redirect", methods=["GET"])
def oauth_redirect():
	return handler.handle(request)

# Commands

@app.command("/add-file")
def add_file_command(ack, respond, body, client):
	if not check_user_permission(client, body["user_id"]):
		ack()
		return respond(app_constants.no_permission_command)

	add_file(ack, body, client)

@app.command("/add-entry")
def add_entry_command(ack, respond, body, client):
	if not check_user_permission(client, body["user_id"]):
		ack()
		return respond(app_constants.no_permission_command)

	add_entry(ack, body, client)

@app.command("/ping")
def test_command(ack):
	ack("Pong!")

# Utilities

def check_user_permission(client, user_id, minimum_permissions="admin"):
	user_info = client.users_info(user=user_id)

	if minimum_permissions == "admin":
		return user_info["user"]["is_admin"]
	elif minimum_permissions == "owner":
		return user_info["user"]["is_owner"]
	elif minimum_permissions == "primary_owner":
		return user_info["user"]["is_primary_owner"]
	else:
		return True

def get_dialogflow_response(text, team_id, user_id):
	existing_knowledge_base = knowledge_base_utils.get_knowledge_base_by_name(
		project_id=project_id,
		knowledge_base_name=team_id
	)

	if existing_knowledge_base is None:
		return f"Hello <@{user_id}>, unfortunately I am not set up yet."

	knowledge_base_id = existing_knowledge_base.name.rpartition("/")[2]

	detected_knowledge = intent_utils.detect_intent_knowledge(
		project_id=project_id,
		session_id=team_id + "_" + user_id,
		language_code="en",
		knowledge_base_id=knowledge_base_id,
		texts=[text]
	)

	unknown_response = app_constants.get_unknown_answer_response()

	# If we got back a potential answer from the knowledge base, use it.
	if detected_knowledge.answers:
		best_answer = detected_knowledge.answers[0]
		response = best_answer.answer

		from google.cloud import dialogflow_v2beta1 as dialogflow
		HIGH = dialogflow.types.KnowledgeAnswers.Answer.MatchConfidenceLevel.HIGH

		# If the best answer doesn't have a high confidence, 
		if best_answer.match_confidence_level != HIGH:
			if response.startswith("|"):
				response = response[1:]

			# For logging purposes (currently unused)
			interaction = {
					"question" : text,
					"response" : unknown_response,
					"best_answer" : response,
					"confidence" : str(best_answer.match_confidence_level),
					"found" : True,
					"sent" : False
				}

			return unknown_response

		document = document_utils.get_document_by_id(
			project_id=project_id,
			knowledge_base_id=knowledge_base_id,
			document_id=best_answer.source.rpartition("/")[2]
		)

		# Add the context footer to the message depending on the source.
		if document.display_name.startswith(app_constants.manual_entry_header):
			footer = app_constants.manual_entry_context_footer
			document_type = "Manual Entry"
			response = response[1:]
		elif document.display_name.startswith(app_constants.learned_entry_header):
			footer = app_constants.learned_entry_context_footer
			document_type = "Learned Entry"
			response = response[1:]
		else:
			document_type = "Bulk file"
			footer =  app_constants.file_context_footer

		# For logging purposes (currently unused)
		interaction = {
					"question" : text,
					"response" : response,
					"confidence" : str(best_answer.match_confidence_level),
					"found" : True,
					"sent" : True,
					"document_type" : document_type
				}

		return response + footer
	else:
		# For logging purposes (currently unused)
		interaction = {
					"question" : text,
					"response" : unknown_response,
					"found" : False,
					"sent" : False
				}

		return unknown_response

def upload_question_answer_pair(question, answer, client, context, ack=None, learned=False):
	team_id = context["team_id"]

	# Format the data within the file to allow for cleaner seperation later. We don't want to partition in the wrong place.
	raw_content = f'"{question}","|{answer}"'
	uid = hashlib.md5(raw_content.encode()).hexdigest()

	# Construct the filename using the appropriate entry header. This ensures it will be unique and identifiable.
	file_name = f"{app_constants.learned_entry_header if learned else app_constants.manual_entry_header}|{uid}.csv"

	existing_knowledge_base = knowledge_base_utils.get_knowledge_base_by_name(
		project_id=project_id,
		knowledge_base_name=team_id
	)

	if not existing_knowledge_base and ack:
		ack(response_action="errors", errors={"add-entry-input-question":"This workspace has not been setup yet!", "add-entry-input-answer":"This workspace has not been setup yet!"})
		return False
	elif not existing_knowledge_base:
		return False

	knowledge_base_id = existing_knowledge_base.name.rpartition("/")[2]

	documents_response = document_utils.list_documents(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id
	)

	# Iterate over the documents to load them all in.
	documents = [x for x in documents_response]

	existing_document = [x for x in documents if os.path.splitext(x.display_name)[0].endswith(f"{uid}")]

	if not existing_document and team_id in uploading_entries:
		for document in uploading_entries[team_id]:
			if os.path.splitext(document[1].display_name)[0].endswith(f"{uid}"):
				existing_document = document

	# If this exact entry already exists, reject it.
	if existing_document and ack:
		ack(response_action="errors", errors={"add-entry-input-question":"This entry already exists!", "add-entry-input-answer":"This entry already exists!"})
		return False
	elif existing_document:
		return False

	if ack:
		ack()

	entry_data = (learned, file_name, question, answer)

	# Cache that we are uploading the entry for local display purposes.
	if team_id not in uploading_entries:
		uploading_entries[team_id] = []
	uploading_entries[team_id].append(entry_data)

	update_app_home(client, context)

	document_utils.create_document(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id,
		display_name=file_name,
		mime_type="text/csv",
		knowledge_type="FAQ",
		raw_content=raw_content.encode("utf-8")
	)

	# Remove the entry from the uploading cache and reupdate the app home.
	uploading_entries[team_id].remove(entry_data)

	if not uploading_entries[team_id]:
		uploading_entries.pop(team_id)

	update_app_home(client, context)

	return True

def update_app_home(client, context):
	team_id = context["team_id"]
	user_id = context["user_id"]

	# Don't show the user if they don't have permission.
	if not check_user_permission(client, user_id):
		return client.views_publish(
			user_id=user_id,
			view=app_constants.app_home_no_permissions_view
		)

	existing_knowledge_base = knowledge_base_utils.get_knowledge_base_by_name(
		project_id=project_id,
		knowledge_base_name=team_id
	)

	if existing_knowledge_base is None:
		return client.views_publish(
			user_id=user_id,
			view=app_constants.app_home_no_knowledge_base_view
		)

	knowledge_base_id = existing_knowledge_base.name.rpartition("/")[2]

	# Get this workspace's documents and classify them.
	documents_response = document_utils.list_documents(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id
	)

	# Iterate over the documents to load them all in.
	documents = [x for x in documents_response]

	# Get the cached entry uploads and removals if there are any.
	uploaded_entries = uploading_entries.get(team_id, [])
	removed_entries = removing_entries.get(team_id, [])

	# Classify entries based on their header. Remove any entries also currently being removed.
	manual_entries = [x for x in documents if x.display_name.startswith(app_constants.manual_entry_header) and x not in removed_entries]
	learned_entries = [x for x in documents if x.display_name.startswith(app_constants.learned_entry_header) and x not in removed_entries]

	# Get the cached file uploads and removals if there are any.
	uploaded_files = uploading_files.get(team_id, [])
	removed_files = removing_files.get(team_id, [])

	# Anything that wasn't an entry was a file. Remove any files also currently being removed.
	files = [x for x in documents if not x.display_name.startswith(app_constants.manual_entry_header) and not x.display_name.startswith(app_constants.learned_entry_header) and not x in removed_files]

	view = {
			"type": "home",
			"blocks": []
		}

	# Add the Manual Entry section.
	view["blocks"].append(app_constants.app_home_manual_entry_header_view)
	view["blocks"].append(app_constants.app_home_add_manual_entry_button_view)
	view["blocks"].append(app_constants.divide)

	# Add uploading manual entries.
	for entry in uploaded_entries:
		learned, file_name, question, answer = entry
		if not learned:
			view["blocks"].append(app_constants.app_home_uploading_manual_entry_view(question, answer))
			view["blocks"].append(app_constants.divide)

	# Add each manual entry.
	if manual_entries:
		for document in manual_entries:
			# Skip the ones that are uploading as we already displayed those.
			for uploading_entry in uploaded_entries:
				if document.display_name == uploading_entry[1]:
					break
			else:
				# Get the text out of the file and remove the first and last quote.
				raw_content = document.raw_content.decode("utf-8")[1:-1]
				
				# Partition the text around the attempted unique separator.
				question, sep, answer = raw_content.partition('","|')
				view["blocks"].append(app_constants.app_home_manual_entry_view(document.display_name, question, answer))
				view["blocks"].append(app_constants.divide)

	# Let the user know if they don't have any manual entries.
	elif not [x for x in uploaded_entries if not x[0]]: # if not learned
		view["blocks"].append(app_constants.app_home_no_manual_entries_view)
		view["blocks"].append(app_constants.divide)

	# Add the Learned Entry section if there are any.
	if learned_entries or [x for x in uploaded_entries if x[0]]:
		view["blocks"].append(app_constants.app_home_learned_entry_header_view)
		view["blocks"].append(app_constants.divide)

		# Add uploading learned entries.
		for entry in uploaded_entries:
			learned, file_name, question, answer = entry
			if learned:
				view["blocks"].append(app_constants.app_home_uploading_learned_entry_view(question, answer))
				view["blocks"].append(app_constants.divide)

		# Add each learned entry.
		for document in learned_entries:
			for uploading_entry in uploaded_entries:
				# Skip the ones that are uploading as we already displayed those.
				if document.display_name == uploading_entry[1]:
					break
			else:
				raw_content = document.raw_content.decode("utf-8")[1:-1]
				question, sep, answer = raw_content.partition('","|')
				view["blocks"].append(app_constants.app_home_learned_entry_view(document.display_name, question, answer))
				view["blocks"].append(app_constants.divide)

	# Add the File section.
	view["blocks"].append(app_constants.app_home_file_header_view)
	view["blocks"].append(app_constants.app_home_add_file_button_view)
	view["blocks"].append(app_constants.divide)

	# Add uploading files.
	for document in uploaded_files:
		view["blocks"].append(app_constants.app_home_uploading_file_view(document))
		view["blocks"].append(app_constants.divide)

	# Add each file.
	if files:
		for document in files:
			for uploading_document in uploaded_files:
				# Skip the ones that are uploading as we already displayed those.
				if document.display_name == uploading_document:
					break
			else:
				view["blocks"].append(app_constants.app_home_file_view(document.display_name))
				view["blocks"].append(app_constants.divide)

	# Let the user know if they don't have any files.
	elif team_id not in uploading_files:
		view["blocks"].append(app_constants.app_home_no_files_view)
		view["blocks"].append(app_constants.divide)

	client.views_publish(
		user_id=user_id,
		view=view
	)

# Event Listeners

@app.event("app_uninstalled")
def handle_app_uninstalled(context):
	team_id = context["team_id"]

	# Delete installation / authentification data.
	app.installation_store.delete_all(
		enterprise_id=None,
		team_id=team_id
	)

	# Delete DialogFlow data.
	existing_knowledge_base = knowledge_base_utils.get_knowledge_base_by_name(
		project_id=project_id,
		knowledge_base_name=team_id
	)

	if existing_knowledge_base is None:
		return

	knowledge_base_id = existing_knowledge_base.name.rpartition("/")[2]

	knowledge_base_utils.delete_knowledge_base(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id
	)

@app.event("app_home_opened")
def handle_app_home_opened(client, event, context):
	update_app_home(client, context)

@app.event("app_mention")
def handle_mention(event, say):
	text = re.sub(app_constants.mention_pattern, '', event["text"])
	team_id = event["team"]
	user_id = event["user"]

	say(get_dialogflow_response(text, team_id, user_id), thread_ts=event.get("thread_ts", None))

@app.event("message")
def handle_message(message, client, say, context, event):
	if not "text" in message:
		return

	text = re.sub(app_constants.mention_pattern, '', message["text"])
	team_id = message["team"]
	user_id = message["user"]
	ts = message["ts"]
	channel_id = message["channel"]

	# Check if someone direct messaged a question.
	if message["channel_type"] == "im":
		return say(get_dialogflow_response(text, team_id, user_id), thread_ts=message.get("thread_ts", None))

	# Maybe an instructor was replying to a question? Check and see.
	if not check_user_permission(client, user_id):
		return

	question = None
	answer = None

	message_link_search = app_constants.message_link_pattern.search(text)

	# Check if this is a linked reply to a question.
	if message_link_search:
		groups = message_link_search.groupdict()

		# Correct the ts value to the format Slack wants.
		groups["ts"] = f"{groups['ts'][:-6]}.{groups['ts'][-6:]}"

		# Get the linked message containing the question.
		response = client.conversations_history(
			channel=groups["channel"],
			latest=groups["ts"],
			inclusive=True,
			limit=1
		)

		if response["ok"] and response["messages"]:
			question = response["messages"][0]["text"]
			answer = groups["answer"]
	# Check if this is a threaded reply to a question.
	elif "thread_ts" in message and ts != message["thread_ts"]:
		# Get the parent message containing the question.
		response = client.conversations_history(
			channel=channel_id,
			latest=message["thread_ts"],
			inclusive=True,
			limit=1
		)

		if response["ok"] and response["messages"]:
			question = response["messages"][0]["text"]
			answer = text
	# Check if this is a shared reply to a question.
	elif "attachments" in message and message["attachments"]:
		shared_message_attachment = message["attachments"][0]

		if "text" in shared_message_attachment:
			# Get the shared text containing the question.
			question = shared_message_attachment["text"]
			answer = text

	# If we found a valid answer, try to learn it and add a reaction to the answer message.
	if question and answer:
		if upload_question_answer_pair(question, answer, client, context, learned=True):
			client.reactions_add(
				channel=channel_id,
				timestamp=ts,
				name="brain",
			)

# Actions

@app.action("add_file")
def add_file(ack, body, client):
	ack()

	client.views_open(
		trigger_id=body["trigger_id"],
		view=app_constants.add_file_view
	)

@app.action("remove_file")
def remove_file(ack, context, payload, client):
	team_id = context["team_id"]
	document_name = payload["value"]

	existing_knowledge_base = knowledge_base_utils.get_knowledge_base_by_name(
		project_id=project_id,
		knowledge_base_name=team_id
	)

	if existing_knowledge_base is None:
		return

	knowledge_base_id = existing_knowledge_base.name.rpartition("/")[2]

	document = document_utils.get_document_by_name(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id,
		document_name=document_name
	)

	if document is None:
		return

	document_id = document.name.rpartition("/")[2]

	ack()

	# Cache that we are removing the file for local display purposes.
	if team_id not in removing_files:
		removing_files[team_id] = []
	removing_files[team_id].append(document)

	update_app_home(client, context)

	document_utils.delete_document(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id,
		document_id=document_id
	)

	# Remove the file from the removing cache and reupdate the app home.
	removing_files[team_id].remove(document)

	if not removing_files[team_id]:
		removing_files.pop(team_id)

	update_app_home(client, context)

@app.action("add_entry")
def add_entry(ack, body, client):
	ack()

	client.views_open(
		trigger_id=body["trigger_id"],
		view=app_constants.add_entry_view
	)

@app.action("remove_entry")
def remove_entry(ack, context, payload, client):
	team_id = context["team_id"]
	document_name = payload["value"]

	existing_knowledge_base = knowledge_base_utils.get_knowledge_base_by_name(
		project_id=project_id,
		knowledge_base_name=team_id
	)

	if existing_knowledge_base is None:
		return

	knowledge_base_id = existing_knowledge_base.name.rpartition("/")[2]

	document = document_utils.get_document_by_name(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id,
		document_name=document_name
	)

	if document is None:
		return

	document_id = document.name.rpartition("/")[2]

	ack()

	# Cache that we are removing the entry for local display purposes.
	if team_id not in removing_entries:
		removing_entries[team_id] = []
	removing_entries[team_id].append(document)

	update_app_home(client, context)

	document_utils.delete_document(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id,
		document_id=document_id
	)

	# Remove the file from the removing cache and reupdate the app home.
	removing_entries[team_id].remove(document)

	if not removing_entries[team_id]:
		removing_entries.pop(team_id)

	update_app_home(client, context)

# View submissions

@app.view("add-file-submission")
def view_add_file_submission(ack, client, view, context):
	url = view["state"]["values"]["add-file-input"]["url"]["value"]
	
	try:
		response = urllib.request.urlopen(url)
	except Exception:
		ack(response_action="errors", errors={"add-file-input":"File could not be retrieved."})
		return

	raw_content = response.read()
	file_info = response.info()
	file_name = file_info.get_filename()
	mime_type = file_info.get_content_type()

	if mime_type in document_utils.FAQ_MIME:
		knowledge_type = "FAQ"
	elif mime_type in document_utils.EXTRACTIVE_QA_MIME:
		knowledge_type = "EXTRACTIVE_QA"
	else:
		ack(response_action="errors", errors={"add-file-input":"Unknown file type"})
		return

	team_id = context["team_id"]

	existing_knowledge_base = knowledge_base_utils.get_knowledge_base_by_name(
		project_id=project_id,
		knowledge_base_name=team_id
	)

	if existing_knowledge_base is None:
		ack(response_action="errors", errors={"add-file-input":"This workspace has not been setup yet!"})
		return

	knowledge_base_id = existing_knowledge_base.name.rpartition("/")[2]

	existing_document = document_utils.get_document_by_name(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id,
		document_name=file_name)

	if not existing_document and team_id in uploading_files:
		for document in uploading_files[team_id]:
			if document == file_name:
				existing_document = document

	# If this exact entry already exists, reject it.
	if existing_document:
		ack(response_action="errors", errors={"add-file-input":"This entry already exists!"})
		return

	ack()

	# Cache that we are uploading the file for local display purposes.
	if team_id not in uploading_files:
		uploading_files[team_id] = []
	uploading_files[team_id].append(file_name)

	update_app_home(client, context)

	document_utils.create_document(
		project_id=project_id,
		knowledge_base_id=knowledge_base_id,
		display_name=file_name,
		mime_type=mime_type,
		knowledge_type=knowledge_type,
		raw_content=raw_content
	)

	# Remove the file from the uploading cache and reupdate the app home.
	uploading_files[team_id].remove(file_name)

	if not uploading_files[team_id]:
		uploading_files.pop(team_id)

	update_app_home(client, context)

@app.view("add-entry-submission")
def view_add_entry_submission(ack, client, body, view, context):
	question = view["state"]["values"]["add-entry-input-question"]["question"]["value"]
	answer = view["state"]["values"]["add-entry-input-answer"]["answer"]["value"]
	upload_question_answer_pair(question, answer, client, context, ack)