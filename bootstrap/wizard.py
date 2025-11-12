#!/usr/bin/env python3
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual import on
from textual.widgets import Header, Footer, Static, Button

from screens.network_screen import NetworkScreen
from screens.activation_screen import ActivationScreen
from screens.summary_screen import SummaryScreen


class BootstrapWizard(App):
    """Unified network + activation wizard."""
    CSS_PATH = None
    TITLE = "Device Setup Wizard"

    def on_mount(self):
        self.push_screen(NetworkScreen(on_done=self.after_network))

    def after_network(self, network_result: dict):
        """Called after the network screen completes."""
        if not network_result.get("connected"):
            self.push_screen(SummaryScreen(result={"error": "Network not connected"}))
            return
        self.push_screen(ActivationScreen(on_done=self.after_activation))

    def after_activation(self, activation_result: dict):
        self.push_screen(SummaryScreen(result=activation_result))


if __name__ == "__main__":
    BootstrapWizard().run()
