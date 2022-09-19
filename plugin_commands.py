from .plugin import SESSION_NAME
from http.server import BaseHTTPRequestHandler, HTTPServer
from LSP.plugin import LspTextCommand, Request, Session
from LSP.plugin.core.protocol import Location
from LSP.plugin.core.typing import Any, Callable, List, Optional, Union
from threading import Thread
from urllib.parse import urlparse, parse_qs
import base64
import re
import sublime
import weakref
import webbrowser


class LspGrammarlyCommand(LspTextCommand):
    session_name = SESSION_NAME
    msg_prefix = "LSP-Grammarly: "
    weaksession = None  # type: Optional[weakref.ref[Session]]
    cmd = None  # type: Optional[str]

    def error_message(self, msg: str) -> None:
        sublime.error_message(self.msg_prefix + msg)

    def message_dialog(self, msg: str) -> None:
        sublime.message_dialog(self.msg_prefix + msg)

    def send_request_with_callback(self, params: Any, callback: Callable[[Union[List[Location], None]], None]) -> None:
        def run_async() -> None:
            if not self.cmd:
                return
            session = self.session_by_name()
            if not session:
                return
            self.weaksession = weakref.ref(session)
            request = Request(self.cmd, params, None, progress=True)
            session.send_request(request, callback, self._on_error_async)
        sublime.set_timeout_async(run_async)

    def send_request(self, params: Any) -> None:
        self.send_request_with_callback(params, self._on_success_async)

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

    def _on_success_async(self, auth_url: Optional[str]) -> None:
        if not auth_url:
            return
        link = self._prepare_link(self.external_redirect_uri, auth_url)
        session = self.weaksession and self.weaksession()
        if session:
            webbrowser.open(link, autoraise=True)
            session.window.show_input_panel(
                "Follow the in-browser instructions and paste here the final URL after the indirection:", "",
                lambda r: self._send_response_async(r), None, lambda: self._send_response_async(None))

    def _prepare_link(self, redirect_uri: str, response: str) -> str:
        return re.sub("state=[^&]*",
                      "state=" + base64.b64encode(bytes(redirect_uri, 'utf-8')).decode('ascii'),
                      response)

    def _send_response_async(self, uri: Optional[str]) -> None:
        if uri:
            res = urlparse(uri)
            if res.scheme != 'vscode':
                self.error_message("Unexpected authorization URL schema. Hint: the inputted authorization URL should start with 'vscode://'")
                return
            if self.weaksession:
                self._send_authorization_url(uri, self.weaksession)

    def _send_authorization_url(self, authorization_url: str, weaksession: 'weakref.ref[Session]') -> None:
        session = weaksession and weaksession()
        if session:
            request = Request(self.cmd_callback, authorization_url, None, progress=True)
            session.send_request(
                request, lambda _: self.view.run_command("lsp_grammarly_execute_is_connected"),
                lambda _: self.error_message("Invalid authorization-response url."))

    def _on_error_async(self, error: Any) -> None:
        self.error_message("Failed to start login process")


class LspGrammarlyExecuteLoginThroughThirdPartyCommand(LspGrammarlyExecuteLoginCommand):
    """
    We piggyback on VSCode client's functionality and redirect utility.

    To avoid the forbidden redirect to localhost, we use the same
    netlify function as the VSCode plugin to redirect to the localhost.
    **Without any guarantee**, the VSCode netlify functions should be
    running the code from here:
    https://github.com/znck/grammarly/blob/main/redirect/functions/redirect.js
    """
    redirect_uri = 'https://vscode-extension-grammarly.netlify.app/.netlify/functions/redirect'
    localhost_qs = '?vscode-scheme=vscode&vscode-authority=znck.grammarly&vscode-path=/auth/callback'

    def run(self, edit: sublime.Edit) -> None:
        session = self.session_by_name()
        if not session:
            return

        weaksession = weakref.ref(session)
        weaklogincmd = weakref.ref(self)

        class HandleAuthResponse(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(r"""
                    <html>
                        <link rel="icon" href="data:;base64,iVBORw0KGgo=">
                        <head><title>LSP-Grammarly</title></head>
                        <body onload="window.close()">
                            LSP-Grammarly: You can close this tab
                        </body>
                    </html>""".encode('utf-8'))
                logincmd = weaklogincmd()
                if not logincmd:
                    return
                if not self.path:
                    return
                qkeys = parse_qs(self.path)
                code = qkeys["code"]
                if not code:
                    return
                input = LspGrammarlyExecuteLoginThroughThirdPartyCommand.internal_redirect_uri + '?code=' + code[0]
                logincmd._send_authorization_url(input, weaksession)

        server = HTTPServer(('localhost', 0), HandleAuthResponse)
        server.timeout = 5 * 60  # 5 min

        final_auth_link = 'http://localhost:' + str(server.server_address[1]) + self.localhost_qs

        def on_success_async_with_server(response: Union[List[Location], None]) -> None:
            if not response:
                return

            link = self._prepare_link(final_auth_link, str(response))
            webbrowser.open(link, autoraise=True)

            def run_async() -> None:
                server.handle_request()
                server.server_close()

            thrd = Thread(target=run_async)
            thrd.daemon = True
            thrd.start()

        self.send_request_with_callback(self.redirect_uri, on_success_async_with_server)


class LspGrammarlyExecuteLogoutCommand(LspGrammarlyCommand):
    cmd = "$/logout"

    def run(self, edit: sublime.Edit) -> None:
        self.send_request(None)

    def _on_success_async(self, response: None) -> None:
        self.message_dialog("Logged out")

    def _on_error_async(self, error: Any) -> None:
        self.error_message("Failed to logout")


class LspGrammarlyExecuteIsConnectedCommand(LspGrammarlyCommand):
    cmd = "$/isUserAccountConnected"

    def run(self, edit: sublime.Edit) -> None:
        self.send_request(None)

    def _on_success_async(self, logged_in: bool) -> None:
        self.message_dialog("Logged-in" if logged_in else "Not logged-in")

    def _on_error_async(self, error: Any) -> None:
        self.error_message("Failed to query whether logged in: " + str(error))
