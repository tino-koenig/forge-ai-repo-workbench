class RepoContext:
    def __init__(self, root="."):
        self.root = root

    def describe(self):
        return f"Repo at {self.root}"