from src.core import Core

from direct.showbase.ShowBase import ShowBase


class App:
    def __init__(self):
        core = Core(verbose=True)
        core.setup()


base = ShowBase()
App()
base.run()
