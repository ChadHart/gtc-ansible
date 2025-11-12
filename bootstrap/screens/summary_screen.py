from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static, Button, Label
from textual.containers import Vertical
from textual import on

class SummaryScreen(Screen):
    """Final confirmation screen."""

    def __init__(self, result: dict):
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        yield Static("Setup Summary", classes="title")
        msg = ""
        if self.result.get("error"):
            msg = f"❌ {self.result['error']}"
        elif self.result.get("activated"):
            msg = "✅ Device activated and ready!"
        elif self.result.get("connected"):
            msg = f"✅ Connected to network. IP: {self.result.get('ip')}"
        else:
            msg = "⚠️  Setup incomplete."
        yield Label(msg)
        yield Button("Finish", id="finish", variant="success")

    @on(Button.Pressed, "#finish")
    def exit_wizard(self):
        self.app.exit(self.result)
