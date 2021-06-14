# https://github.com/googleapis/python-dialogflow/blob/master/samples/snippets/knowledge_base_management.py
from google.cloud import dialogflow_v2beta1 as dialogflow

knowledge_base_cache = {}

def create_knowledge_base(project_id, display_name):
	"""Creates a Knowledge base.
	Args:
	    project_id: The GCP project linked with the agent.
	    display_name: The display name of the Knowledge base."""
	client = dialogflow.KnowledgeBasesClient()
	project_path = client.common_project_path(project_id)

	knowledge_base = dialogflow.KnowledgeBase(display_name=display_name)

	try:
		response = client.create_knowledge_base(parent=project_path, knowledge_base=knowledge_base)
		response.result(timeout=120)
	except Exception:
		response = None

	return response

def get_knowledge_base_by_id(project_id, knowledge_base_id):
	"""Gets a specific Knowledge base.
	Args:
	    project_id: The GCP project linked with the agent.
	    knowledge_base_id: Id of the Knowledge base."""
	client = dialogflow.KnowledgeBasesClient()
	knowledge_base_path = client.knowledge_base_path(project_id, knowledge_base_id)

	try:
		response = client.get_knowledge_base(name=knowledge_base_path)
	except Exception:
		response = None

	return response

def get_knowledge_base_by_name(project_id, knowledge_base_name):
	"""Gets a specific Knowledge base.
	Args:
	    project_id: The GCP project linked with the agent.
	    knowledge_base_name: Display name of the Knowledge base."""
	if knowledge_base_name in knowledge_base_cache:
		return knowledge_base_cache[knowledge_base_name]

	list_knowledge_bases(project_id)

	return knowledge_base_cache.get(knowledge_base_name, None)

def list_knowledge_bases(project_id):
	"""Gets a list of all Knowledge base.
	Args:
	    project_id: The GCP project linked with the agent."""
	client = dialogflow.KnowledgeBasesClient()
	project_path = client.common_project_path(project_id)

	try:
		response = client.list_knowledge_bases(parent=project_path)

		for knowledge_base in response:
			knowledge_base_cache[knowledge_base.display_name] = knowledge_base
	except Exception:
		response = None

	return response

def delete_knowledge_base(project_id, knowledge_base_id):
	"""Deletes a specific Knowledge base.
	Args:
	    project_id: The GCP project linked with the agent.
	    knowledge_base_id: Id of the Knowledge base."""
	client = dialogflow.KnowledgeBasesClient()
	
	knowledge_base_path = client.knowledge_base_path(project_id, knowledge_base_id)
	
	# Use DeleteKnowledgeBaseRequest because delete_knowledge_base doesn't expose force.
	request = dialogflow.DeleteKnowledgeBaseRequest(name=knowledge_base_path, force=True)

	knowledge_base = get_knowledge_base_by_id(project_id, knowledge_base_id)

	from dialogflow_utils.document_utils import list_documents, document_cache
	documents = list_documents(project_id, knowledge_base_id)

	for document in documents:
		document_cache.pop(knowledge_base_id + "_" + document.display_name)

	knowledge_base_cache.pop(knowledge_base.display_name)

	client.delete_knowledge_base(request)