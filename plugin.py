from __future__ import annotations

from LSP.plugin import LspPlugin
from LSP.plugin import notification_handler
from LSP.plugin import OnPreStartContext
from LSP.plugin import parse_uri
from lsp_utils import NodeManager
from pathlib import Path
from sublime_lib import ResourcePath
from typing import final
from typing_extensions import override

STATUS_KEY = 'lsp-grammarly'


@final
class LspGrammarlyPlugin(LspPlugin):

    @classmethod
    @override
    def on_pre_start_async(cls, context: OnPreStartContext) -> None:
        package_name = cls.plugin_storage_path.name
        NodeManager.on_pre_start_async(
            context,
            cls.plugin_storage_path,
            ResourcePath('Packages', package_name, 'grammarly-languageserver'),
            Path('node_modules', 'grammarly-languageserver', 'bin', 'server.js'),
            node_version_requirement='^16.13.0 || 17',
        )

    @notification_handler("$/onDocumentStatus")
    def onDocumentStatus(self, params: dict[str, str]) -> None:
        if "uri" not in params or "status" not in params:
            return
        session = self.weaksession()
        if not session:
            return
        _, filename = parse_uri(params["uri"])
        status_key = f"{STATUS_KEY}_checking"
        for sv in session.session_views_async():
            if sv.view.is_valid() and filename == sv.view.file_name():
                if params["status"] == "idle":
                    sv.view.erase_status(status_key)
                else:
                    sv.view.set_status(status_key, f"{STATUS_KEY}: {params['status']}")


def plugin_loaded() -> None:
    LspGrammarlyPlugin.register()


def plugin_unloaded() -> None:
    LspGrammarlyPlugin.unregister()
