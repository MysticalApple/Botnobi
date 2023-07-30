import json


def clean_code(content):
    if content.startswith("```") and content.endswith("```"):
        return "\n".join(content.split("\n")[1:][:-1])

    return content


def config_get(option):
    with open("config.json", "r") as config_file:
        config = json.load(config_file)
        return config[option]


def config_set(option, value):
    with open("config.json", "r") as config_file:
        config = json.load(config_file)

    try:
        if type(config[option]) == int:
            config[option] = value

            with open("config.json", "w") as config_file:
                json.dump(config, config_file)

        else:
            raise

    # Returns an error if the value is not a bool or if it does not exist
    except:
        print("config set incorrectly i think")