import sublime

import os
import re
import base64
from urllib.parse import urlparse, parse_qs
import weakref

from LSP.plugin.core.protocol import Request, Location
from LSP.plugin.core.typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, TypedDict, Union
from LSP.plugin.core.registry import LspTextCommand
from LSP.plugin import register_plugin, unregister_plugin
from LSP.plugin import AbstractPlugin, ClientConfig, SessionBufferProtocol
from LSP.plugin import WorkspaceFolder
from LSP.plugin.core.types import Optional, Any, Tuple, List
from lsp_utils import ApiWrapperInterface, NpmClientHandler

class LspGrammarlyCommand(LspTextCommand):
    session_name = 'grammarly'

class LspGrammarlyExecuteLoginCommand(LspGrammarlyCommand):
    cmd = "$/getOAuthUrl"
    cmd_callback = "$/handleOAuthCallbackUri"

    internal_redirect_uri = "vscode://znck.grammarly/auth/callback"
    external_redirect_uri = internal_redirect_uri
    redirect_uri = internal_redirect_uri

    def run(self, edit: sublime.Edit) -> None:
        def run_async() -> None:
            session = self.session_by_name()
            if session:
                request = Request(self.cmd, self.redirect_uri, None, progress=True)
                self.weaksession = weakref.ref(session)
                session.send_request(request, self._handle_response,
                    lambda r: print(self.cmd, r))
            else:
                self._handle_resolve_response_async(None, item)
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
            assert(res.scheme == 'vscode')
            request = Request(self.cmd_callback, input, None, progress=True)
            session = self.weaksession()
            if session:
                session.send_request(request, lambda p: print("Connected." + str(p)),
                    lambda r: print("Invalid authorization-response url"))
        else:
            print("Logging cancelled")


class LspGrammarlyExecuteLogoutCommand(LspGrammarlyCommand):
    cmd = "$/logout"

    def run(self, edit: sublime.Edit) -> None:
        def run_async() -> None:
            session = self.session_by_name()
            assert(session)
            request = Request(self.cmd, None, None, progress=True)
            session.send_request(request, self._handle_response,
                lambda r: print("Failed to logout: " + str(r)))
        sublime.set_timeout_async(run_async)

    def _handle_response(self, response: Union[List[Location], None]) -> None:
        if response:
            print("Logout response: " + str(response))
        else:
            print("Logged out")

class LspGrammarlyExecuteIsConnectedCommand(LspGrammarlyCommand):
    cmd = "$/isUserAccountConnected"

    def run(self, edit: sublime.Edit) -> None:
        def run_async() -> None:
            session = self.session_by_name()
            assert(session)
            request = Request(self.cmd, None, None, progress=True)
            session.send_request(request, self._handle_response,
                lambda r: print("Failed to query whether connected: " + str(r)))
        sublime.set_timeout_async(run_async)

    def _handle_response(self, response: Union[List[Location], None]) -> None:
        if response:
            print("Connected: " + str(response))
        else:
            print("Not connected")

class LspGrammarlyPlugin(NpmClientHandler):
    package_name = "LSP-grammarly"
    server_directory = 'grammarly-languageserver'
    server_binary_path = os.path.join(
        server_directory, 'grammarly-languageserver', 'packages', 'grammarly-languageserver', 'bin', 'server.js'
    )
    
    @classmethod
    def name(cls) -> str:
        return LspGrammarlyCommand.session_name
    
    @classmethod
    def minimum_node_version(cls) -> Tuple[int, int, int]:
        return (16, 13, 0)
    
    def handle_status_response(self, status, is_error):
        if is_error:
            print("Requesting status failed")
    
    def m___onDocumentStatus(self, params):
        print(params)
    
    def m___onUserAccountConnectedChange(self, params):
        print("User account connected: " + str(params["isUserAccountConnected"]))
    
    def on_pre_server_command(self, command: Mapping[str, Any], done_callback: Callable[[], None]) -> bool:
        if command["command"] == 'grammarly.dismiss' and "arguments" in command:
            dismissList = command["arguments"]
            session = self.weaksession()
            request = Request("$/dismissSuggestion", [dismissList], None, progress=True)
            session.send_request(request, lambda p: None, lambda p: print("Error: " + str(p)))
            done_callback()
            return True
        return super().on_pre_server_command(command, done_callback)

def plugin_loaded() -> None:
    register_plugin(LspGrammarlyPlugin)

def plugin_unloaded() -> None:
    unregister_plugin(LspGrammarlyPlugin)
