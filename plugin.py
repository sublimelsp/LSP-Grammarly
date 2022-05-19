import sublime

import os
import re
import base64
from urllib.parse import urlparse
import weakref

from LSP.plugin.core.protocol import Request, Location
from LSP.plugin.core.sessions import Session
from LSP.plugin.core.typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union
from LSP.plugin.core.registry import LspTextCommand
from LSP.plugin import register_plugin, unregister_plugin
from lsp_utils import NpmClientHandler


class LspGrammarlyCommand(LspTextCommand):
    session_name = 'grammarly'
    msg_prefix = "LSP-Grammarly: "
    weaksession = None  # type: Optional[weakref.ref[Session]]
    cmd = None  # type: Optional[str]

    def error_message(self, msg: str) -> None:
        sublime.error_message(self.msg_prefix + msg)

    def message_dialog(self, msg: str) -> None:
        sublime.message_dialog(self.msg_prefix + msg)

    def send_request(self, params: Any) -> None:
        def run_async() -> None:
            if not self.cmd:
                return
            session = self.session_by_name()
            if not session:
                return
            self.weaksession = weakref.ref(session)
            request = Request(self.cmd, params, None, progress=True)
            session.send_request(request, self._on_success_async, self._on_error_async)
        sublime.set_timeout_async(run_async)

    def _on_success_async(self, response: Any) -> None:
        raise NotImplementedError()

    def _on_error_async(self, error: Any) -> None:
        pass


class LspGrammarlyExecuteLoginCommand(LspGrammarlyCommand):
    cmd = "$/getOAuthUrl"
    cmd_callback = "$/handleOAuthCallbackUri"

    internal_redirect_uri = "vscode://znck.grammarly/auth/callback"
    external_redirect_uri = internal_redirect_uri
    redirect_uri = internal_redirect_uri

    def run(self, edit: sublime.Edit) -> None:
        self.send_request(self.redirect_uri)

    def _on_success_async(self, response: Union[List[Location], None]) -> None:
        link = re.sub("state=[^&]*",
                      "state=" + base64.b64encode(bytes(self.external_redirect_uri, 'utf-8')).decode('ascii'),
                      str(response))
        session = self.weaksession and self.weaksession()
        if session:
            session.window.show_input_panel(
                "Open this url in the browser and paste in its place the redirection:", link,
                lambda r: self._send_response_async(r), None, lambda: self._send_response_async(None))

    def _on_error_async(self, error: Any) -> None:
        self.error_message("Failed to start login process")

    def _send_response_async(self, input: Optional[str]) -> None:
        if input:
            res = urlparse(input)
            if res.scheme != 'vscode':
                self.error_message("Unexpected authorization URL schema. Hint: the inputted authorization URL should start with 'vscode://'")
                return
            request = Request(self.cmd_callback, input, None, progress=True)
            session = self.weaksession and self.weaksession()
            if session:
                session.send_request(
                    request, lambda p: None,
                    lambda _: self.error_message("Invalid authorization-response url. Did it start with 'vscode://'?"))


class LspGrammarlyExecuteLogoutCommand(LspGrammarlyCommand):
    cmd = "$/logout"

    def run(self, edit: sublime.Edit) -> None:
        self.send_request(None)

    def _on_success_async(self, response: Union[List[Location], None]) -> None:
        if response:
            self.message_dialog("Logout response: " + str(response))
        else:
            self.message_dialog("Logged out")

    def _on_error_async(self, error: Any) -> None:
        self.error_message("Failed to logout")


class LspGrammarlyExecuteIsConnectedCommand(LspGrammarlyCommand):
    cmd = "$/isUserAccountConnected"

    def run(self, edit: sublime.Edit) -> None:
        self.send_request(None)

    def _on_success_async(self, response: Union[List[Location], None]) -> None:
        if response:
            self.message_dialog("Connected: " + str(response))
        else:
            self.message_dialog("Not connected")

    def _on_error_async(self, error: Any) -> None:
        self.error_message("Failed to query whether connected: " + str(error))


class LspGrammarlyPlugin(NpmClientHandler):
    package_name = "LSP-Grammarly"
    server_directory = "grammarly-languageserver"
    server_binary_path = os.path.join(server_directory, "node_modules", "grammarly-languageserver", "bin", "server.js")

    @classmethod
    def name(cls) -> str:
        return LspGrammarlyCommand.session_name

    @classmethod
    def minimum_node_version(cls) -> Tuple[int, int, int]:
        return (16, 13, 0)

    def m___onDocumentStatus(self, params: Dict[str, str]) -> None:
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
            assert(session)
            request = Request("$/dismissSuggestion", [dismissals], None, progress=True)
            session.send_request(request, lambda p: None)
            done_callback()
            return True
        return super().on_pre_server_command(command, done_callback)


def plugin_loaded() -> None:
    register_plugin(LspGrammarlyPlugin)


def plugin_unloaded() -> None:
    unregister_plugin(LspGrammarlyPlugin)
