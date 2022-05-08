import json


def clean_code(content):
    if content.startswith("```") and content.endswith("```"):
        return "\n".join(content.split("\n")[1:][:-1])

    return content


def check_toggle(feature):
    with open("config.json", "r") as config_file:
        config = json.load(config_file)
        return config[feature]


def get_alerts_channel_id():
    with open("config.json", "r") as config_file:
        config = json.load(config_file)
        return config["alerts_channel_id"]
