from __future__ import annotations

from LSP.plugin import notification_handler
from LSP.plugin import parse_uri
from LSP.plugin import register_plugin
from LSP.plugin import unregister_plugin
from lsp_utils import NpmClientHandler
from typing import final
from typing_extensions import override
import os

SESSION_NAME = 'grammarly'


@final
class LspGrammarlyPlugin(NpmClientHandler):
    package_name = "LSP-Grammarly"
    server_directory = "grammarly-languageserver"
    server_binary_path = os.path.join(server_directory, "node_modules", "grammarly-languageserver", "bin", "server.js")

    @classmethod
    @override
    def name(cls) -> str:
        return SESSION_NAME

    @classmethod
    @override
    def required_node_version(cls) -> str:
        return "^16.13.0 || 17"

    @notification_handler("$/onDocumentStatus")
    def onDocumentStatus(self, params: dict[str, str]) -> None:
        if "uri" not in params or "status" not in params:
            return
        session = self.weaksession()
        if not session:
            return
        _, filename = parse_uri(params["uri"])
        status_key = self.name() + "_checking"
        for sv in session.session_views_async():
            if sv.view.is_valid() and filename == sv.view.file_name():
                if params["status"] == "idle":
                    sv.view.erase_status(status_key)
                else:
                    sv.view.set_status(status_key, self.name() + ": " + params["status"])


def plugin_loaded() -> None:
    register_plugin(LspGrammarlyPlugin)


def plugin_unloaded() -> None:
    unregister_plugin(LspGrammarlyPlugin)
