from . import models
from . import controllers
from . import wizards


def post_init_hook(cr, registry):
    # Run optional post-init routine (logs that Sales AI is initialized)
    from . import claude_training

    claude_training.run(cr, registry)

