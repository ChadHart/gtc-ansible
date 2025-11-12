from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static, Button, Label, ListView, ListItem, Input
from textual.containers import Vertical, Horizontal
from textual import on
from utils.nmcli_utils import scan_networks, connect_network, get_connectivity, get_ip_address

class NetworkScreen(Screen):
    """Wi-Fi selection and connection."""

    def __init__(self, on_done):
        super().__init__()
        self.on_done = on_done
        self.networks = []
        self.selected_ssid = None

    def compose(self) -> ComposeResult:
        yield Static("Wi-Fi Setup", classes="title")
        self.listview = ListView(id="networks")
        yield self.listview
        self.password = Input(password=True, placeholder="Password (if required)")
        yield self.password
        with Horizontal():
            yield Button("Refresh", id="refresh")
            yield Button("Connect", id="connect", variant="primary")
            yield Button("Continue", id="done", variant="success")
        self.status = Label("")
        yield self.status

    async def on_mount(self):
        await self.refresh_networks()

    async def refresh_networks(self):
        self.status.update("Scanning…")
        self.networks = await scan_networks()
        self.listview.clear()
        for net in self.networks:
            self.listview.append(ListItem(Label(f"{net['ssid']}  ({net['signal']}%)")))
        self.status.update(f"Found {len(self.networks)} network(s).")

    @on(ListView.Selected)
    def handle_select(self, event: ListView.Selected):
        self.selected_ssid = self.networks[event.index]["ssid"]

    @on(Button.Pressed, "#refresh")
    async def handle_refresh(self):
        await self.refresh_networks()

    @on(Button.Pressed, "#connect")
    async def handle_connect(self):
        if not self.selected_ssid:
            self.status.update("Select a network first.")
            return
        self.status.update(f"Connecting to {self.selected_ssid}…")
        ok, msg = await connect_network(self.selected_ssid, self.password.value)
        if ok:
            ip = await get_ip_address()
            self.status.update(f"Connected! IP: {ip or 'unknown'}")
        else:
            self.status.update(f"Failed: {msg}")

    @on(Button.Pressed, "#done")
    async def handle_done(self):
        connected = await get_connectivity()
        ip = await get_ip_address()
        self.on_done({"connected": connected, "ip": ip})
