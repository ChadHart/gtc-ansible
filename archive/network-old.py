#!/usr/bin/env python3
"""
Textual TUI Network Wizard
- Scans Wi-Fi networks with nmcli
- Lets user select an SSID or enter a hidden SSID
- Prompts for password when needed
- Connects and verifies connectivity
- Displays IP address(es)

Requires:
  - Python 3.9+
  - textual (pip install textual)
  - NetworkManager (nmcli)
"""

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, Static, Button, Input, Label, ListView, ListItem
)
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive

# --------- Helpers (non-UI) ---------

def have_nmcli() -> bool:
    return shutil.which("nmcli") is not None

def linux_only():
    if platform.system().lower() != "linux":
        raise RuntimeError("This wizard currently supports Linux with NetworkManager (nmcli).")

@dataclass
class WifiNetwork:
    ssid: str
    signal: int      # 0-100
    security: str    # e.g., WPA2, WPA3, --, etc.

def run(cmd: List[str], timeout: int = 8) -> Tuple[int, str, str]:
    """Run a command and return (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"

def scan_wifi() -> List[WifiNetwork]:
    """
    Use nmcli to list available Wi-Fi networks.
    Output columns: SSID,SIGNAL,SECURITY
    """
    rc, out, err = run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"])
    networks: List[WifiNetwork] = []
    if rc != 0:
        return networks
    seen = set()
    for line in out.splitlines():
        parts = line.split(":")
        # nmcli -t uses ':' as delimiter; SSID itself can contain ':', so rebuild carefully:
        if len(parts) >= 3:
            ssid = ":".join(parts[:-2]).strip()
            signal = parts[-2].strip()
            security = parts[-1].strip() or "--"
            print(f"Debug: Found network SSID='{ssid}', SIGNAL='{signal}', SECURITY='{security}'", file=sys.stderr)
            if not ssid:
                ssid = "(hidden)"
            if ssid not in seen:
                try:
                    sig = int(signal)
                except ValueError:
                    sig = 0
                networks.append(WifiNetwork(ssid=ssid, signal=sig, security=security))
                seen.add(ssid)
    # Sort by signal desc, then by name
    networks.sort(key=lambda n: (-n.signal, n.ssid.lower()))
    return networks

def connect_wifi(ssid: str, password: Optional[str]) -> Tuple[bool, str]:
    """
    Connect to Wi-Fi using nmcli.
    For open networks, password can be None or "".
    """
    if ssid == "(hidden)":
        return False, "Cannot directly connect to '(hidden)'—please use 'Hidden SSID' flow."
    # Try to connect
    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    rc, out, err = run(cmd, timeout=25)
    if rc == 0:
        return True, out or "Connected."
    return False, err or out or "Failed to connect."

def connect_hidden_wifi(ssid: str, password: Optional[str]) -> Tuple[bool, str]:
    """
    For hidden SSIDs, create or modify a connection profile and bring it up.
    """
    if not ssid:
        return False, "SSID cannot be empty."
    # Attempt a direct connection first (nmcli can handle hidden with ssid provided)
    cmd = ["nmcli", "device", "wifi", "connect", ssid, "hidden", "yes"]
    if password:
        cmd += ["password", password]
    rc, out, err = run(cmd, timeout=25)
    if rc == 0:
        return True, out or "Connected."
    # Fallback: add a connection profile explicitly
    # Note: Security guess—most hidden networks are secured; for open hidden, omit wifi-sec args.
    if password:
        add = [
            "nmcli", "connection", "add",
            "type", "wifi", "con-name", ssid, "ifname", "*",
            "ssid", ssid, "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password
        ]
    else:
        add = [
            "nmcli", "connection", "add",
            "type", "wifi", "con-name", ssid, "ifname", "*",
            "ssid", ssid
        ]
    rc2, out2, err2 = run(add, timeout=15)
    if rc2 != 0 and "exists" not in (out2 + err2).lower():
        return False, err2 or out2 or "Failed to create connection profile."
    rc3, out3, err3 = run(["nmcli", "connection", "up", ssid], timeout=20)
    if rc3 == 0:
        return True, out3 or "Connected."
    return False, err3 or out3 or "Failed to bring up connection."

def have_connectivity(timeout: float = 3.0) -> bool:
    """
    Simple connectivity check: try DNS + HTTPS quickly.
    """
    # Quick DNS check
    try:
        socket.gethostbyname("www.google.com")
    except Exception:
        return False
    # Quick HTTP(S) check via curl/wget/python
    try:
        rc, out, err = run(["curl", "-sS", "--max-time", str(int(timeout)), "https://www.google.com/generate_204"], timeout=int(timeout)+1)
        if rc == 0:
            return True
    except Exception:
        pass
    return False

def get_ip_addresses() -> List[str]:
    """
    Return current IPv4 addresses from 'hostname -I' or 'ip -4 addr'.
    """
    rc, out, _ = run(["hostname", "-I"])
    if rc == 0 and out:
        # hostname -I returns space-separated IPs, may end with space
        ips = [ip.strip() for ip in out.strip().split() if ip.strip()]
        return ips
    rc2, out2, _ = run(["ip", "-4", "-o", "addr", "show"])
    ips = []
    if rc2 == 0:
        for line in out2.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                addr = parts[3]  # e.g., 192.168.1.10/24
                ip = addr.split("/")[0]
                ips.append(ip)
    return ips

# --------- TUI ---------

class NetworkWizard(App):
    CSS = """
    Screen {
        align: center middle;
    }
    .box {
        width: 80%;
        max-width: 100;
        border: round $primary;
        padding: 1 2;
    }
    .row { width: 100%; }
    .title { content-align: center middle; }
    .hint { color: $text-muted; }
    """

    selected_ssid: reactive[str | None] = reactive(None)
    networks: reactive[list] = reactive([])
    status_text: reactive[str] = reactive("")
    connected_ips: reactive[list] = reactive([])

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(classes="box"):
            yield Static("Wi-Fi Setup Wizard", classes="title")
            yield Static("Select a network from the list, or choose 'Hidden SSID' to enter one manually.", classes="hint")
            self.listview = ListView(id="netlist")
            yield self.listview
            with Horizontal(classes="row"):
                yield Button("Refresh", id="refresh")
                yield Button("Hidden SSID", id="hidden")
                yield Button("Connect", id="connect", variant="primary")
            self.password_input = Input(password=True, placeholder="Password (leave empty for open network)", id="password")
            yield self.password_input
            self.status_label = Label("", id="status")
            yield self.status_label
            self.ip_label = Label("", id="ip")
            yield self.ip_label
            with Horizontal(classes="row"):
                yield Button("Check Connectivity", id="check")
                yield Button("Done", id="done", variant="success")
        yield Footer()

    async def on_mount(self) -> None:
        linux_only()
        if not have_nmcli():
            self.status_text = "Error: 'nmcli' not found. Please install NetworkManager."
            self.status_label.update(self.status_text)
            return
        await self.refresh_scan()

    async def refresh_scan(self):
        self.status_text = "Scanning for Wi-Fi networks..."
        self.status_label.update(self.status_text)
        self.listview.clear()
        self.networks = scan_wifi()
        if not self.networks:
            self.status_text = "No networks found. Ensure your Wi-Fi is enabled."
            self.status_label.update(self.status_text)
            return
        for net in self.networks:
            display = f"{net.ssid}   [{net.security}]   {net.signal}%"
            self.listview.append(ListItem(Label(display), id=f"ssid::{net.ssid}"))
        self.status_text = f"Found {len(self.networks)} network(s)."
        self.status_label.update(self.status_text)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is None:
            return
        item_id = event.item.id or ""
        if item_id.startswith("ssid::"):
            self.selected_ssid = item_id.split("ssid::", 1)[1]

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id
        if btn == "refresh":
            await self.refresh_scan()
        elif btn == "hidden":
            await self.enter_hidden_ssid()
        elif btn == "connect":
            await self.attempt_connect()
        elif btn == "check":
            await self.do_connectivity_check()
        elif btn == "done":
            # Return a JSON payload to the caller through exit()
            payload = {
                "connected": have_connectivity(),
                "ips": get_ip_addresses(),
            }
            self.exit(json.dumps(payload))

    async def enter_hidden_ssid(self):
        # Minimal inline prompt for hidden SSID name
        self.status_text = "Enter hidden SSID in the password field temporarily, then press Connect. (We'll reprompt for password)"
        self.status_label.update(self.status_text)
        self.selected_ssid = "(hidden-enter-next)"
        self.password_input.placeholder = "TEMP: Enter hidden SSID here, then press Connect"
        self.password_input.password = False
        self.password_input.value = ""

    async def attempt_connect(self):
        if self.selected_ssid is None:
            self.status_text = "Select a network first (or choose Hidden SSID)."
            self.status_label.update(self.status_text)
            return

        if self.selected_ssid == "(hidden-enter-next)":
            ssid_entered = self.password_input.value.strip()
            if not ssid_entered:
                self.status_text = "Hidden SSID cannot be empty."
                self.status_label.update(self.status_text)
                return
            # Switch input back to password mode and prompt for password
            self.selected_ssid = ssid_entered
            self.password_input.value = ""
            self.password_input.password = True
            self.password_input.placeholder = "Password for hidden SSID (leave empty if open), then press Connect again"
            self.status_text = f"Hidden SSID '{ssid_entered}' captured. Enter password (if any), then press Connect again."
            self.status_label.update(self.status_text)
            return

        pwd = self.password_input.value or None

        self.status_text = f"Connecting to '{self.selected_ssid}'..."
        self.status_label.update(self.status_text)
        self.set_widgets_enabled(False)
        try:
            if self.selected_ssid == "(hidden)":
                ok, msg = False, "Please use 'Hidden SSID' to enter the network name."
            else:
                # Determine if this SSID likely needs a password based on scan result
                needs_pwd = True
                for n in self.networks:
                    if n.ssid == self.selected_ssid:
                        needs_pwd = (n.security not in ("--", "NONE", ""))
                        break
                if not needs_pwd:
                    pwd = None
                # For a hidden network explicitly entered, use hidden flow:
                if self.selected_ssid and not any(n.ssid == self.selected_ssid for n in self.networks):
                    ok, msg = connect_hidden_wifi(self.selected_ssid, pwd)
                else:
                    ok, msg = connect_wifi(self.selected_ssid, pwd)

            if ok:
                # Give DHCP a moment
                time.sleep(2)
                ips = get_ip_addresses()
                self.connected_ips = ips
                self.status_text = f"Connected to '{self.selected_ssid}'."
                if ips:
                    self.ip_label.update("IP: " + ", ".join(ips))
                else:
                    self.ip_label.update("IP: (pending DHCP)")
            else:
                self.status_text = f"Connection failed: {msg}"
        finally:
            self.status_label.update(self.status_text)
            self.set_widgets_enabled(True)

    async def do_connectivity_check(self):
        self.status_text = "Checking internet connectivity..."
        self.status_label.update(self.status_text)
        ok = have_connectivity()
        ips = get_ip_addresses()
        self.connected_ips = ips
        if ips:
            self.ip_label.update("IP: " + ", ".join(ips))
        else:
            self.ip_label.update("IP: (none)")
        self.status_text = "Online ✅" if ok else "Offline ❌"
        self.status_label.update(self.status_text)

    def set_widgets_enabled(self, enabled: bool):
        self.query_one("#refresh", Button).disabled = not enabled
        self.query_one("#hidden", Button).disabled = not enabled
        self.query_one("#connect", Button).disabled = not enabled
        self.query_one("#check", Button).disabled = not enabled
        self.query_one("#done", Button).disabled = not enabled
        self.query_one("#password", Input).disabled = not enabled


def run_network_wizard() -> dict:
    """
    Launch the Textual TUI and return a dict summary:
      {
        "connected": bool,
        "ips": [list of IP strings]
      }
    """
    linux_only()
    app = NetworkWizard()
    result = app.run()
    try:
        return json.loads(result) if result else {"connected": False, "ips": []}
    except Exception:
        return {"connected": have_connectivity(), "ips": get_ip_addresses()}


if __name__ == "__main__":
    out = run_network_wizard()
    # Print minimal output so a caller can parse stdout if desired
    print(json.dumps(out))
