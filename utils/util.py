import json

config_path = "config.json"

def config_get(option):
    with open(config_path, "r") as config_file:
        config = json.load(config_file)
        return config[option]


def config_set(option, value):
    with open(config_path, "r") as config_file:
        config = json.load(config_file)

    try:
        if isinstance(config[option], int):
            config[option] = value

            with open(config_path, "w") as config_file:
                json.dump(config, config_file)

        else:
            raise ValueError

    # Returns an error if the value is not a bool or if it does not exist
    except Exception:
        print("config set incorrectly i think")


def clean_code(content):
    if content.startswith("```") and content.endswith("```"):
        return "\n".join(content.split("\n")[1:][:-1])

    return content