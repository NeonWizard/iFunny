def _default(message, args):
    return

def _help(message, args):
    """
    List commands
    """
    _help = f"my prefixes are {', '.join(list(message.client.prefix))}"
    for command in message.client.commands:
        command = message.client.commands[command]
        _help += f"{command.name}: {command.help if command.help else 'no docstring'}\n"

    message.send(_help)

class Command:
    def __init__(self, method, name, cog = None):
        self.method = method
        self.name = name
        self.help = self.method.__doc__
        cog = cog

    def __call__(self, message, args):
        return self.method(message, args)

class Defaults:

    help = Command(_help, "help")

    default = Command(_default, "default")
