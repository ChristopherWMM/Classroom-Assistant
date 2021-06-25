import re
import random

install_data_path = "./data/bolt-app-installation"

# File-name headers for manual/learned entries
manual_entry_header = "Manual_Entry"
learned_entry_header = "Learned_Entry"

# Missing permission messages
no_permission_app_home = ":sweat: I'm sorry, you don't have permission to view this..."
no_permission_command = ":sweat: I'm sorry, you don't have permission to do that..."

# Context footers
manual_entry_context_footer = "\n\n> :pencil: This information was provided to me manually by your instructor."
learned_entry_context_footer = "\n\n> :brain: I learned this based on previous questions your instructor has answered."
file_context_footer = "\n\n> :page_with_curl: This information was extracted from a file provided to me by your instructor."

message_link_pattern = re.compile("<https://(?P<team>\S+\.slack\.com)/archives/(?P<channel>\S+)/p(?P<ts>\d+)>\s*(?P<answer>.+$)")
mention_pattern = re.compile("\s*<@[\w|\d]+>\s*")

unknown_answer_responses_prefixes = [
	"Sorry",
	"I'm sorry",
	"Hm"
]

unknown_answer_responses = [
	"I am having some trouble understanding that.",
	"I don't think I know anything about that.",
	"I don't understand your question.",
	"I don't think I have been taught that yet.",
	"I don't believe I have learned anything about that yet."
]

unknown_answer_responses_suffixes = [
	"Can you try to rephrase your question? :sweat:"
]

def get_unknown_answer_response():
	prefix = random.choice(unknown_answer_responses_prefixes)
	body = random.choice(unknown_answer_responses)
	suffix = random.choice(unknown_answer_responses_suffixes)
	return f"{prefix}, {body} {suffix}"

add_file_view = {
	"type": "modal",
	"callback_id": "add-file-submission",
	"title": {
		"type": "plain_text",
		"text": "Add File",
	},
	"submit": {
		"type": "plain_text",
		"text": "Submit",
	},
	"close": {
		"type": "plain_text",
		"text": "Cancel",
	},
	"blocks": [
		{
			"type": "input",
			"block_id": "add-file-input",
			"element": {
				"type": "plain_text_input",
				"action_id": "url",
				"placeholder": {
					"type": "plain_text",
					"text": "Direct link to your new file"
				}
			},
			"label": {
				"type": "plain_text",
				"text": "Add new knowledge",
			},
		}
	],
}

add_entry_view = {
	"type": "modal",
	"callback_id": "add-entry-submission",
	"title": {
		"type": "plain_text",
		"text": "New Entry",
		"emoji": True
	},
	"submit": {
		"type": "plain_text",
		"text": "Submit",
		"emoji": True
	},
	"type": "modal",
	"close": {
		"type": "plain_text",
		"text": "Cancel",
		"emoji": True
	},
	"blocks": [
		{
			"type": "input",
			"block_id": "add-entry-input-question",
			"element": {
				"type": "plain_text_input",
				"action_id": "question",
				"placeholder": {
					"type": "plain_text",
					"text": "Expected question"
				}
			},
			"label": {
				"type": "plain_text",
				"text": "Question"
			}
		},
		{
			"type": "input",
			"block_id": "add-entry-input-answer",
			"element": {
				"type": "plain_text_input",
				"action_id": "answer",
				"placeholder": {
					"type": "plain_text",
					"text": "Desired answer"
				}
			},
			"label": {
				"type": "plain_text",
				"text": "Answer"
			}
		}
	]
}

divide = {
	"type": "divider"
}

app_home_no_permissions_view = {
	"type": "home",
	"blocks": [
		{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": f"{no_permission_app_home}"
			}
		}
	]
}

app_home_no_knowledge_base_view = {
	"type": "home",
	"blocks": [
		{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": ":wrench: Setting up Classroom Assistant"
			}
		}
	]
}

app_home_manual_entry_header_view = {
					"type": "header",
					"text": {
						"type": "plain_text",
						"text": ":pencil: Entries"
					}
				}

app_home_add_manual_entry_button_view = {
					"type": "section",
					"text": {
						"type": "mrkdwn",
						"text": " "
					},
					"accessory": {
						"type": "button",
						"text": {
							"type": "plain_text",
							"emoji": True,
							"text": "Add Entry"
						},
						"style": "primary",
						"value": "click_me_123",
						"action_id": "add_entry"
					}
				}

def app_home_uploading_manual_entry_view(question, answer):
	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"_Uploading..._\n*Question:*\n> {question}\n*Answer:*\n> {answer}"
		}
	}

def app_home_manual_entry_view(file_name, question, answer):
	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"*Question:*\n> {question}\n*Answer:*\n> {answer}"
		},
		"accessory": {
			"type": "button",
			"text": {
				"type": "plain_text",
				"emoji": True,
				"text": "Remove"
			},
			"style": "danger",
			"value": f"{file_name}",
			"action_id": "remove_entry",
			"confirm": {
				"title": {
					"type": "plain_text",
					"text": "Manual Entry"
				},
				"text": {
					"type": "mrkdwn",
					"text": f"Are you sure you want to remove this entry?"
				},
				"confirm": {
					"type": "plain_text",
					"text": "Yes, remove it"
				},
				"deny": {
					"type": "plain_text",
					"text": "Cancel"
				},
				"style": "danger"
			}
		}
	}

app_home_no_manual_entries_view = {
					"type": "section",
					"text": {
						"type": "plain_text",
						"text": ":open_file_folder: You don't have any manual entries yet!",
						"emoji": True
					}
				}

app_home_learned_entry_header_view = {
					"type": "header",
					"text": {
						"type": "plain_text",
						"text": ":brain: Learned Entries"
					}
				}

def app_home_uploading_learned_entry_view(question, answer):
	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"_Uploading..._\n*Question:*\n> {question}\n*Answer:*\n> {answer}"
		}
	}

def app_home_learned_entry_view(file_name, question, answer):
	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"*Question:*\n> {question}\n*Answer:*\n> {answer}"
		},
		"accessory": {
			"type": "button",
			"text": {
				"type": "plain_text",
				"emoji": True,
				"text": "Remove"
			},
			"style": "danger",
			"value": f"{file_name}",
			"action_id": "remove_entry",
			"confirm": {
				"title": {
					"type": "plain_text",
					"text": "Learned Entry"
				},
				"text": {
					"type": "mrkdwn",
					"text": f"Are you sure you want to remove this entry?"
				},
				"confirm": {
					"type": "plain_text",
					"text": "Yes, remove it"
				},
				"deny": {
					"type": "plain_text",
					"text": "Cancel"
				},
				"style": "danger"
			}
		}
	}

app_home_file_header_view = {
					"type": "header",
					"text": {
						"type": "plain_text",
						"text": ":page_with_curl: Files"
					}
				}

app_home_add_file_button_view = {
					"type": "section",
					"text": {
						"type": "mrkdwn",
						"text": " "
					},
					"accessory": {
						"type": "button",
						"text": {
							"type": "plain_text",
							"emoji": True,
							"text": "Add File"
						},
						"style": "primary",
						"value": "click_me_123",
						"action_id": "add_file"
					}
				}

def app_home_uploading_file_view(file_name):
	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"_Uploading..._\n*{file_name}*"
		}
	}

def app_home_file_view(file_name):
	return {
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": f"*{file_name}*"
		},
		"accessory": {
			"type": "button",
			"text": {
				"type": "plain_text",
				"emoji": True,
				"text": "Remove"
			},
			"style": "danger",
			"value": f"{file_name}",
			"action_id": "remove_file",
			"confirm": {
				"title": {
					"type": "plain_text",
					"text": f"{file_name}"
				},
				"text": {
					"type": "mrkdwn",
					"text": f"Are you sure you want to remove {file_name}?"
				},
				"confirm": {
					"type": "plain_text",
					"text": "Yes, remove it"
				},
				"deny": {
					"type": "plain_text",
					"text": "Cancel"
				},
				"style": "danger"
			}
		}
	}

app_home_no_files_view = {
					"type": "section",
					"text": {
						"type": "plain_text",
						"text": ":open_file_folder: You don't have any files yet!",
						"emoji": True
					}
				}