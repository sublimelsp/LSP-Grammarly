import sublime

import os
import re
import base64
from urllib.parse import urlparse
import weakref

from LSP.plugin.core.protocol import Request, Location
from LSP.plugin.core.typing import Any, Callable, List, Mapping, Optional, Tuple, Union
from LSP.plugin.core.registry import LspTextCommand
from LSP.plugin import register_plugin, unregister_plugin
from lsp_utils import NpmClientHandler

class LspGrammarlyCommand(LspTextCommand):
    session_name = 'grammarly'
    msg_prefix = "LSP-Grammarly: "

    def error_message(self, msg: str) -> None:
        sublime.error_message(self.msg_prefix + msg)

    def message_dialog(self, msg: str) -> None:
        sublime.message_dialog(self.msg_prefix + msg)

class LspGrammarlyExecuteLoginCommand(LspGrammarlyCommand):
    cmd = "$/getOAuthUrl"
    cmd_callback = "$/handleOAuthCallbackUri"

    internal_redirect_uri = "vscode://znck.grammarly/auth/callback"
    external_redirect_uri = internal_redirect_uri
    redirect_uri = internal_redirect_uri

    def run(self, edit: sublime.Edit) -> None:
        def run_async() -> None:
            session = self.session_by_name()
            self.weaksession = weakref.ref(session)
            if session:
                request = Request(self.cmd, self.redirect_uri, None, progress=True)
                session.send_request(request, self._handle_response,
                    lambda r: self.error_message("Failed to start login process"))
        sublime.set_timeout_async(run_async)

    def _handle_response(self, response: Union[List[Location], None]) -> None:
        link = re.sub("state=[^&]*", "state=" + base64.b64encode(bytes(self.external_redirect_uri, 'utf-8')).decode('ascii'), str(response))
        session = self.weaksession()
        if session:
            session.window.show_input_panel("Open this url in the browser and paste in its place the redirection:", link,
                                     lambda r: self._send_response(r), None, lambda: self._send_response(None))

    def _send_response(self, input: Optional[str]) -> None:
        if input:
            res = urlparse(input)
            if res.scheme != 'vscode':
                self.error_message("Unexpected authorization URL schema. Hint: the inputted authorization URL should start with 'vscode://'")
                return
            request = Request(self.cmd_callback, input, None, progress=True)
            session = self.weaksession()
            if session:
                session.send_request(request, lambda p: None,
                    lambda r: self.error_message("Invalid authorization-response url. Did it start with 'vscode://'?"))

class LspGrammarlyExecuteLogoutCommand(LspGrammarlyCommand):
    cmd = "$/logout"

    def run(self, edit: sublime.Edit) -> None:
        def run_async() -> None:
            session = self.session_by_name()
            assert(session)
            request = Request(self.cmd, None, None, progress=True)
            session.send_request(request, self._handle_response,
                lambda r: self.error_message("Failed to logout"))
        sublime.set_timeout_async(run_async)

    def _handle_response(self, response: Union[List[Location], None]) -> None:
        if response:
            self.message_dialog("Logout response: " + str(response))
        else:
            self.message_dialog("Logged out")

class LspGrammarlyExecuteIsConnectedCommand(LspGrammarlyCommand):
    cmd = "$/isUserAccountConnected"

    def run(self, edit: sublime.Edit) -> None:
        def run_async() -> None:
            session = self.session_by_name()
            if not session:
                return
            request = Request(self.cmd, None, None, progress=True)
            session.send_request(request, self._handle_response,
                lambda r: self.error_message("Failed to query whether connected: " + str(r)))
        sublime.set_timeout_async(run_async)

    def _handle_response(self, response: Union[List[Location], None]) -> None:
        if response:
            self.message_dialog("Connected: " + str(response))
        else:
            self.message_dialog("Not connected")

class LspGrammarlyPlugin(NpmClientHandler):
    package_name = "LSP-Grammarly"
    server_directory = "grammarly-languageserver"
    server_binary_path = os.path.join(
        server_directory, "node_modules", "grammarly-languageserver", "bin", "server.js"
    )

    @classmethod
    def name(cls) -> str:
        return LspGrammarlyCommand.session_name
    
    @classmethod
    def minimum_node_version(cls) -> Tuple[int, int, int]:
        return (16, 13, 0)

    def m___onDocumentStatus(self, params):
        if "uri" not in params or "status" not in params:
            return
        session = self.weaksession()
        if not session:
            return
        furi = urlparse(params["uri"])
        filename = os.path.abspath(os.path.join(furi.netloc, furi.path))
        skey = self.name() + "_checking"
        for sv in session.session_views_async():
            if sv.view.is_valid() and filename == sv.view.file_name():
                if params["status"] == "idle":
                    sv.view.erase_status(skey)
                else:
                    sv.view.set_status(skey, self.name() + ": " + params["status"])

    def on_pre_server_command(self, command: Mapping[str, Any], done_callback: Callable[[], None]) -> bool:
        if command["command"] == "grammarly.dismiss" and "arguments" in command:
            dismissals = command["arguments"]
            session = self.weaksession()
            request = Request("$/dismissSuggestion", [dismissals], None, progress=True)
            session.send_request(request, lambda p: None)
            done_callback()
            return True
        return super().on_pre_server_command(command, done_callback)

def plugin_loaded() -> None:
    register_plugin(LspGrammarlyPlugin)

def plugin_unloaded() -> None:
    unregister_plugin(LspGrammarlyPlugin)
