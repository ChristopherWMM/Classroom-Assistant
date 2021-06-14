# https://github.com/googleapis/python-dialogflow/blob/master/samples/snippets/document_management.py
from google.cloud import dialogflow_v2beta1 as dialogflow

KNOWLEDGE_TYPES = ['KNOWLEDGE_TYPE_UNSPECIFIED', 'FAQ', 'EXTRACTIVE_QA', 'ARTICLE_SUGGESTION']
FAQ_MIME = ["text/csv"]
EXTRACTIVE_QA_MIME = ["text/html", "text/plain", "application/pdf"]

document_cache = {}

def create_document(project_id, knowledge_base_id, display_name, mime_type, knowledge_type, content_uri=None, raw_content=None):
	"""Creates a Document.
	Args:
	    project_id: The GCP project linked with the agent.
	    knowledge_base_id: Id of the Knowledge base.
	    display_name: The display name of the Document.
	    mime_type: The mime_type of the Document. e.g. text/csv, text/html,
	        text/plain, text/pdf etc.
	    knowledge_type: The Knowledge type of the Document. e.g. FAQ,
	        EXTRACTIVE_QA.
	    content_uri: Uri of the document, e.g. gs://path/mydoc.csv,
	        http://mypage.com/faq.html."""
	client = dialogflow.DocumentsClient()
	knowledge_base_path = dialogflow.KnowledgeBasesClient.knowledge_base_path(project_id, knowledge_base_id)

	if content_uri is not None:
		document = dialogflow.Document(display_name=display_name, mime_type=mime_type, content_uri=content_uri)
	elif raw_content is not None:
		document = dialogflow.Document(display_name=display_name, mime_type=mime_type, raw_content=raw_content)
	else:
		return None

	document.knowledge_types.append(getattr(dialogflow.Document.KnowledgeType, knowledge_type))

	response = client.create_document(parent=knowledge_base_path, document=document)
	document = response.result(timeout=120)

	document_cache[knowledge_base_id + "_" + document.display_name] = document

	return document

def get_document_by_id(project_id, knowledge_base_id, document_id):
	"""Gets a Document.
	Args:
	    project_id: The GCP project linked with the agent.
	    knowledge_base_id: Id of the Knowledge base.
	    document_id: Id of the Document."""
	client = dialogflow.DocumentsClient()
	document_path = client.document_path(project_id, knowledge_base_id, document_id)

	response = client.get_document(name=document_path)

	return response

def get_document_by_name(project_id, knowledge_base_id, document_name):
	"""Gets a Document.
	Args:
	    project_id: The GCP project linked with the agent.
	    knowledge_base_id: Id of the Knowledge base.
	    document_name: Name of the Document."""
	if knowledge_base_id + "_" + document_name in document_cache:
		return document_cache[knowledge_base_id + "_" + document_name]

	list_documents(project_id, knowledge_base_id)

	return document_cache.get(knowledge_base_id + "_" + document_name, None)

def list_documents(project_id, knowledge_base_id):
	"""Lists the Documents belonging to a Knowledge base.
	Args:
	    project_id: The GCP project linked with the agent.
	    knowledge_base_id: Id of the Knowledge base."""
	client = dialogflow.DocumentsClient()
	knowledge_base_path = dialogflow.KnowledgeBasesClient.knowledge_base_path(project_id, knowledge_base_id)

	try:
		response = client.list_documents(parent=knowledge_base_path)

		for document in response:
			document_cache[knowledge_base_id + "_" + document.display_name] = document
	except Exception:
		response = []

	return response

def delete_document(project_id, knowledge_base_id, document_id):
	"""Deletes a Document.
	Args:
	    project_id: The GCP project linked with the agent.
	    knowledge_base_id: Id of the Knowledge base.
	    document_id: Id of the Document."""
	client = dialogflow.DocumentsClient()
	document_path = client.document_path(project_id, knowledge_base_id, document_id)

	document = client.get_document(name=document_path)
	document_cache.pop(knowledge_base_id + "_" + document.display_name)

	response = client.delete_document(name=document_path)
	response.result(timeout=120)