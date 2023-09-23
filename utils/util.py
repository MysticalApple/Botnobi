import json

config_path = "config.json"

# Configs
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


# Github Feed List
def get_feeds_from_file(file):
    """
    Reads in a list of tracked feeds
    """
    feeds = []
    with open(file, "r") as feeds_file:
        for entry in feeds_file.read().strip().split("\n"):
            feed = {"link": entry.split(" ")[0], 
                    "commits": entry.split(" ")[1:]}
            feeds.append(feed)

    return feeds

def write_feeds_to_file(file, feeds):
    """
    Writes a list of tracked feeds to a text file
    """
    with open(file, "w") as feeds_file:
        for feed in feeds:
            feeds_file.write(f"{feed['link']} {' '.join(feed['commits'])}\n")


# Eval Command
def clean_code(content):
    if content.startswith("```") and content.endswith("```"):
        return "\n".join(content.split("\n")[1:][:-1])

    return content