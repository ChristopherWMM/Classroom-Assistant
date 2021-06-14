# https://github.com/googleapis/python-dialogflow/blob/master/samples/snippets/detect_intent_knowledge.py
from google.cloud import dialogflow_v2beta1 as dialogflow

def detect_intent_knowledge(project_id, session_id, language_code, knowledge_base_id, texts):
	"""Returns the result of detect intent with querying Knowledge Connector.
	Args:
	project_id: The GCP project linked with the agent you are going to query.
	session_id: Id of the session, using the same `session_id` between requests
	          allows continuation of the conversation.
	language_code: Language of the queries.
	knowledge_base_id: The Knowledge base's id to query against.
	texts: A list of text queries to send.
	"""
	session_client = dialogflow.SessionsClient()

	session_path = session_client.session_path(project_id, session_id)

	for text in texts:
		text_input = dialogflow.TextInput(text=text, language_code=language_code)

		query_input = dialogflow.QueryInput(text=text_input)

		knowledge_base_path = dialogflow.KnowledgeBasesClient.knowledge_base_path(
			project_id,
			knowledge_base_id
		)

		query_params = dialogflow.QueryParameters(
			knowledge_base_names=[knowledge_base_path]
		)

		request = dialogflow.DetectIntentRequest(
			session=session_path,
			query_input=query_input,
			query_params=query_params
		)

		response = session_client.detect_intent(request=request)

		knowledge_answers = response.query_result.knowledge_answers

		return knowledge_answers