from LSP.plugin import register_plugin, unregister_plugin, uri_to_filename
from LSP.plugin.core.typing import Dict, Tuple
from lsp_utils import NpmClientHandler
import os

SESSION_NAME = 'grammarly'


class LspGrammarlyPlugin(NpmClientHandler):
    package_name = "LSP-Grammarly"
    server_directory = "grammarly-languageserver"
    server_binary_path = os.path.join(server_directory, "node_modules", "grammarly-languageserver", "bin", "server.js")

    @classmethod
    def name(cls) -> str:
        return SESSION_NAME

    @classmethod
    def minimum_node_version(cls) -> Tuple[int, int, int]:
        return (16, 13, 0)

    def m___onDocumentStatus(self, params: Dict[str, str]) -> None:
        if "uri" not in params or "status" not in params:
            return
        session = self.weaksession()
        if not session:
            return
        filename = uri_to_filename(params["uri"])
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
