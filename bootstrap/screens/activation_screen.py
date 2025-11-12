from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static, Button, Input, Label
from textual.containers import Vertical
from textual import on
from utils.api_utils import check_key_status, generate_activation_code
from utils.state_utils import load_state, save_state

class ActivationScreen(Screen):
    """Device activation step."""

    def __init__(self, on_done):
        super().__init__()
        self.on_done = on_done

    def compose(self) -> ComposeResult:
        yield Static("Device Activation", classes="title")
        self.status = Label("Checking device key…")
        yield self.status
        self.key_input = Input(placeholder="Enter API key (optional)")
        yield self.key_input
        yield Button("Validate", id="validate", variant="primary")
        yield Button("Continue", id="done", variant="success")

    async def on_mount(self):
        state = load_state()
        key = state.get("api_key")
        if not key:
            code = generate_activation_code()
            self.status.update(f"No API key found.\nActivation code: {code}")
            state["activation_code"] = code
            save_state(state)
        else:
            ok, msg = await check_key_status(key)
            self.status.update(msg)

    @on(Button.Pressed, "#validate")
    async def validate_key(self):
        key = self.key_input.value.strip()
        if not key:
            self.status.update("Please enter a key.")
            return
        ok, msg = await check_key_status(key)
        self.status.update(msg)
        if ok:
            state = load_state()
            state["api_key"] = key
            save_state(state)

    @on(Button.Pressed, "#done")
    def done(self):
        state = load_state()
        key = state.get("api_key")
        self.on_done({"activated": bool(key)})
