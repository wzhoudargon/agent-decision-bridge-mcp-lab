#!/usr/bin/env python3
"""Streamable HTTP wrapper for the Decision Inbox MCP v1 server."""

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qs, urlencode, urlparse

try:
    from server.decision_inbox_server import handle_request as decision_inbox_handle_request
    from server.decision_inbox_store import DecisionInboxStore, default_tasks_root
    from server.connected_agent_server import (
        FullAgentWorkspaceManager,
        PERMISSION_APPROVAL,
        PERMISSION_CONTROLLED_AUTO,
        PROFILE_CONNECTED_AGENT,
        PROFILE_FULL_AGENT,
        PROFILE_READ_ONLY_PROJECT,
        handle_request as full_agent_handle_request,
        parse_allowed_tasks,
    )
except ModuleNotFoundError:
    from decision_inbox_server import handle_request as decision_inbox_handle_request  # type: ignore
    from decision_inbox_store import DecisionInboxStore, default_tasks_root  # type: ignore
    from connected_agent_server import (  # type: ignore
        FullAgentWorkspaceManager,
        PERMISSION_APPROVAL,
        PERMISSION_CONTROLLED_AUTO,
        PROFILE_CONNECTED_AGENT,
        PROFILE_FULL_AGENT,
        PROFILE_READ_ONLY_PROJECT,
        handle_request as full_agent_handle_request,
        parse_allowed_tasks,
    )


DEFAULT_ALLOWED_ORIGINS = [
    "https://chatgpt.com",
    "https://chat.openai.com",
    "https://platform.openai.com",
]
MODE_AUTO_MCP = "auto-mcp"
MODE_MANUAL = "manual"
MODE_ASK_FIRST = "ask-first"
MODE_READ_ONLY_PROJECT = "read-only-project"
MODE_FULL_AGENT = "full-agent"
MODE_CONNECTED_AGENT = "connected-agent"
VALID_MODES = {
    MODE_AUTO_MCP,
    MODE_MANUAL,
    MODE_ASK_FIRST,
    MODE_READ_ONLY_PROJECT,
    MODE_FULL_AGENT,
    MODE_CONNECTED_AGENT,
}
DEFAULT_FULL_AGENT_STATE_FILE = (
    Path.home() / ".local/share/agent-decision-bridge/oauth-state.json"
)
DEFAULT_FULL_AGENT_OWNER_TOKEN_FILE = (
    Path.home() / ".local/share/agent-decision-bridge/oauth-owner-token"
)


class DecisionInboxHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address,
        RequestHandlerClass,
        store: DecisionInboxStore,
        auth_token: Optional[str],
        allowed_origins: List[str],
        allowed_hosts: Set[str],
        public_base_url: Optional[str],
        oauth_owner_token: Optional[str],
        oauth_scopes: List[str],
        oauth_allowed_redirect_hosts: Set[str],
        oauth_access_token_ttl_seconds: int,
        oauth_refresh_token_ttl_seconds: int,
        oauth_state_file: Optional[Path],
        session_activity_file: Optional[Path],
        mode: str,
        full_agent_manager: Optional[FullAgentWorkspaceManager],
    ):
        super().__init__(server_address, RequestHandlerClass)
        self.mode = mode
        self.store = store
        self.full_agent_manager = full_agent_manager
        self.auth_token = auth_token
        self.allowed_origins = set(allowed_origins)
        self.allowed_hosts = allowed_hosts
        self.public_base_url = public_base_url
        self.oauth_owner_token = oauth_owner_token
        self.oauth_scopes = oauth_scopes
        self.oauth_allowed_redirect_hosts = oauth_allowed_redirect_hosts
        self.oauth_access_token_ttl_seconds = oauth_access_token_ttl_seconds
        self.oauth_refresh_token_ttl_seconds = oauth_refresh_token_ttl_seconds
        self.oauth_state_file = oauth_state_file.expanduser() if oauth_state_file else None
        self.session_activity_file = (
            session_activity_file.expanduser() if session_activity_file else None
        )
        self._session_activity_lock = threading.Lock()
        self.oauth_clients: Dict[str, Dict[str, Any]] = {}
        self.oauth_authorization_codes: Dict[str, Dict[str, Any]] = {}
        self.oauth_access_tokens: Dict[str, Dict[str, Any]] = {}
        self.oauth_refresh_tokens: Dict[str, Dict[str, Any]] = {}
        self._load_oauth_state()

    @property
    def oauth_enabled(self) -> bool:
        return bool(self.oauth_owner_token)

    @property
    def full_agent_enabled(self) -> bool:
        return self.mode == MODE_FULL_AGENT

    @property
    def connected_agent_enabled(self) -> bool:
        return self.mode == MODE_CONNECTED_AGENT

    @property
    def project_workspace_enabled(self) -> bool:
        return self.mode in {MODE_READ_ONLY_PROJECT, MODE_FULL_AGENT, MODE_CONNECTED_AGENT}

    def _load_oauth_state(self) -> None:
        if not self.oauth_state_file or not self.oauth_state_file.is_file():
            return
        try:
            payload = json.loads(self.oauth_state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load OAuth state file: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("OAuth state file must contain a JSON object")
        self.oauth_clients = self._safe_record_map(payload.get("oauth_clients"))
        self.oauth_access_tokens = self._safe_record_map(payload.get("oauth_access_tokens"))
        self.oauth_refresh_tokens = self._safe_record_map(payload.get("oauth_refresh_tokens"))
        if self._drop_expired_oauth_records():
            self.save_oauth_state()

    def save_oauth_state(self) -> None:
        if not self.oauth_state_file:
            return
        payload = {
            "version": 1,
            "oauth_clients": self.oauth_clients,
            "oauth_access_tokens": self.oauth_access_tokens,
            "oauth_refresh_tokens": self.oauth_refresh_tokens,
        }
        self.oauth_state_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp_path = self.oauth_state_file.with_name(
            f".{self.oauth_state_file.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temp_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self.oauth_state_file)
            os.chmod(self.oauth_state_file, 0o600)
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def _drop_expired_oauth_records(self) -> bool:
        now = time.time()
        changed = False
        for mapping in (self.oauth_access_tokens, self.oauth_refresh_tokens):
            expired = [
                token
                for token, record in mapping.items()
                if not isinstance(record.get("expires_at"), (int, float))
                or record["expires_at"] < now
            ]
            for token in expired:
                mapping.pop(token, None)
                changed = True
        return changed

    def _safe_record_map(self, value: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(value, dict):
            return {}
        safe: Dict[str, Dict[str, Any]] = {}
        for key, record in value.items():
            if isinstance(key, str) and isinstance(record, dict):
                safe[key] = record
        return safe

    def touch_session_activity(self) -> None:
        if not self.session_activity_file:
            return
        with self._session_activity_lock:
            try:
                payload = json.loads(self.session_activity_file.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return
            except (OSError, json.JSONDecodeError) as exc:
                print(f"Could not refresh session activity: {exc}", file=sys.stderr)
                return
            if not isinstance(payload, dict):
                return
            payload["last_activity"] = time.time()
            temp_path = self.session_activity_file.with_name(
                f".{self.session_activity_file.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
            )
            try:
                temp_path.write_text(
                    json.dumps(payload, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                os.chmod(temp_path, 0o600)
                os.replace(temp_path, self.session_activity_file)
                os.chmod(self.session_activity_file, 0o600)
            except OSError as exc:
                print(f"Could not refresh session activity: {exc}", file=sys.stderr)
            finally:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass


class DecisionInboxMCPHandler(BaseHTTPRequestHandler):
    server: DecisionInboxHTTPServer

    def do_POST(self) -> None:
        if self._is_oauth_register_path():
            if self._validate_host():
                self._handle_oauth_register()
            return
        if self._is_oauth_authorize_path():
            if self._validate_host():
                self._handle_oauth_authorize_post()
            return
        if self._is_oauth_token_path():
            if self._validate_host():
                self._handle_oauth_token()
            return
        if not self._is_mcp_path():
            self._send_plain(404, "Not found")
            return
        if not self._validate_host():
            return
        if not self._authorize():
            return
        if not self._validate_origin():
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json_error(400, None, -32600, "Invalid Content-Length")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json_error(400, None, -32700, f"Parse error: {exc.msg}")
            return

        response = self._handle_mcp_request(payload)
        if response is None:
            self._debug_jsonrpc(payload, 202)
            self._send_empty(202)
            return
        self._debug_jsonrpc(payload, 200)
        self._send_json(200, response)

    def _handle_mcp_request(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.server.project_workspace_enabled:
            self.server.touch_session_activity()
            if self.server.full_agent_manager is None:
                return self._internal_jsonrpc_error(payload, "Workspace manager is not configured")
            return full_agent_handle_request(payload, self.server.full_agent_manager)
        return decision_inbox_handle_request(payload, self.server.store)

    def _internal_jsonrpc_error(self, payload: Dict[str, Any], message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "error": {"code": -32603, "message": message},
        }

    def do_GET(self) -> None:
        if self._is_protected_resource_metadata_path():
            if self._validate_host():
                self._send_json(200, self._protected_resource_metadata())
            return
        if self._is_oauth_metadata_path():
            if self._validate_host():
                self._send_json(200, self._oauth_metadata())
            return
        if self._is_oauth_authorize_path():
            if self._validate_host():
                self._handle_oauth_authorize_get()
            return
        if not self._is_mcp_path():
            self._send_plain(404, "Not found")
            return
        if not self._validate_host():
            return
        if not self._authorize():
            return
        if not self._validate_origin():
            return
        self._send_empty(405, {"Allow": "POST"})

    def do_DELETE(self) -> None:
        if not self._is_mcp_path():
            self._send_plain(404, "Not found")
            return
        if not self._validate_host():
            return
        if not self._authorize():
            return
        self._send_empty(405, {"Allow": "POST"})

    def do_OPTIONS(self) -> None:
        if self._is_mcp_path():
            self._send_empty(
                204,
                {
                    "Access-Control-Allow-Origin": self.headers.get("Origin", "*"),
                    "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": (
                        "Authorization, Content-Type, Accept, MCP-Protocol-Version, "
                        "Mcp-Session-Id"
                    ),
                },
            )
            return
        self._send_plain(404, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        sanitized_path = urlparse(self.path).path
        message = (format % args).replace(self.path, sanitized_path)
        print(f"{self.address_string()} - {message}", file=sys.stderr)

    def _is_mcp_path(self) -> bool:
        return urlparse(self.path).path.rstrip("/") == "/mcp"

    def _is_protected_resource_metadata_path(self) -> bool:
        path = urlparse(self.path).path.rstrip("/")
        return path in {
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        }

    def _is_oauth_metadata_path(self) -> bool:
        path = urlparse(self.path).path.rstrip("/")
        return path in {
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid-configuration",
        }

    def _is_oauth_register_path(self) -> bool:
        return urlparse(self.path).path.rstrip("/") == "/oauth/register"

    def _is_oauth_authorize_path(self) -> bool:
        return urlparse(self.path).path.rstrip("/") == "/oauth/authorize"

    def _is_oauth_token_path(self) -> bool:
        return urlparse(self.path).path.rstrip("/") == "/oauth/token"

    def _authorize(self) -> bool:
        static_token = self.server.auth_token
        oauth_enabled = self.server.oauth_enabled
        if not static_token and not oauth_enabled:
            return True
        authorization = self.headers.get("Authorization", "")
        if static_token and authorization == f"Bearer {static_token}":
            return True
        query_tokens = parse_qs(urlparse(self.path).query).get("access_token", [])
        if static_token and static_token in query_tokens:
            return True
        if oauth_enabled and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
            if self._oauth_access_token_valid(token):
                return True
        self._send_empty(401, {"WWW-Authenticate": self._www_authenticate_header()})
        return False

    def _oauth_access_token_valid(self, token: str) -> bool:
        record = self.server.oauth_access_tokens.get(token)
        if not record:
            return False
        if record["expires_at"] < time.time():
            self.server.oauth_access_tokens.pop(token, None)
            self.server.save_oauth_state()
            return False
        return bool(set(record.get("scopes", self.server.oauth_scopes)) & set(self.server.oauth_scopes))

    def _www_authenticate_header(self) -> str:
        if not self.server.oauth_enabled:
            return "Bearer"
        scope = " ".join(self.server.oauth_scopes)
        return (
            'Bearer resource_metadata="'
            f"{self._issuer_url()}/.well-known/oauth-protected-resource/mcp"
            f'", scope="{scope}"'
        )

    def _issuer_url(self) -> str:
        if self.server.public_base_url:
            return self.server.public_base_url
        host = self.headers.get("Host") or f"{self.server.server_name}:{self.server.server_port}"
        scheme = "https" if host.endswith(".ts.net") else "http"
        return f"{scheme}://{host}".rstrip("/")

    def _resource_url(self) -> str:
        return f"{self._issuer_url()}/mcp"

    def _protected_resource_metadata(self) -> Dict[str, Any]:
        return {
            "resource": self._resource_url(),
            "authorization_servers": [self._issuer_url()],
            "scopes_supported": self.server.oauth_scopes,
            "resource_name": self._resource_name(),
            "resource_documentation": f"{self._issuer_url()}/mcp",
        }

    def _resource_name(self) -> str:
        if self.server.connected_agent_enabled:
            return "Agent Decision Bridge Connected Agent"
        if self.server.full_agent_enabled:
            return "Agent Decision Bridge Full-Agent"
        if self.server.mode == MODE_READ_ONLY_PROJECT:
            return "Agent Decision Bridge Read-Only Project Advisor"
        return "Agent Decision Bridge Auto MCP Controlled Advisor"

    def _oauth_metadata(self) -> Dict[str, Any]:
        issuer = self._issuer_url()
        return {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth/authorize",
            "token_endpoint": f"{issuer}/oauth/token",
            "registration_endpoint": f"{issuer}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": self.server.oauth_scopes,
        }

    def _handle_oauth_register(self) -> None:
        if not self.server.oauth_enabled:
            self._send_oauth_error(404, "not_found", "OAuth is not enabled")
            return
        try:
            client = self._read_json_body()
        except ValueError as exc:
            self._send_oauth_error(400, "invalid_request", str(exc))
            return

        redirect_uris = client.get("redirect_uris")
        if not isinstance(redirect_uris, list) or not redirect_uris:
            self._send_oauth_error(400, "invalid_client_metadata", "redirect_uris is required")
            return
        if not all(isinstance(uri, str) and self._redirect_uri_allowed(uri) for uri in redirect_uris):
            self._send_oauth_error(400, "invalid_redirect_uri", "redirect_uri is not allowed")
            return

        if self.server.connected_agent_enabled:
            client_prefix = "connected-agent"
        elif self.server.full_agent_enabled:
            client_prefix = "full-agent"
        elif self.server.mode == MODE_READ_ONLY_PROJECT:
            client_prefix = "read-only-project"
        else:
            client_prefix = "auto-mcp"
        client_id = f"{client_prefix}-{uuid.uuid4()}"
        registered = {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": client.get("client_name", "ChatGPT"),
            "redirect_uris": redirect_uris,
            "grant_types": client.get("grant_types", ["authorization_code", "refresh_token"]),
            "response_types": client.get("response_types", ["code"]),
            "token_endpoint_auth_method": client.get("token_endpoint_auth_method", "none"),
        }
        self.server.oauth_clients[client_id] = registered
        self.server.save_oauth_state()
        self._send_json(201, registered)

    def _handle_oauth_authorize_get(self) -> None:
        if not self.server.oauth_enabled:
            self._send_plain(404, "OAuth is not enabled")
            return
        params = {key: values[-1] for key, values in parse_qs(urlparse(self.path).query).items()}
        error = self._validate_authorization_params(params)
        self._send_html(200, self._authorization_form_html(params, error=error))

    def _handle_oauth_authorize_post(self) -> None:
        if not self.server.oauth_enabled:
            self._send_plain(404, "OAuth is not enabled")
            return
        params = self._read_form_body()
        provided_owner_token = params.pop("owner_token", "")
        error = self._validate_authorization_params(params)
        if error:
            self._send_html(400, self._authorization_form_html(params, error=error))
            return
        if not self._safe_equals(provided_owner_token, self.server.oauth_owner_token or ""):
            self._send_html(
                401,
                self._authorization_form_html(
                    params, error="The Owner password was not accepted."
                ),
            )
            return

        code = f"code-{uuid.uuid4()}"
        scopes = self._requested_scopes(params.get("scope"))
        self.server.oauth_authorization_codes[code] = {
            "client_id": params["client_id"],
            "redirect_uri": params["redirect_uri"],
            "code_challenge": params["code_challenge"],
            "resource": params.get("resource") or self._resource_url(),
            "scopes": scopes,
            "expires_at": time.time() + 300,
        }
        redirect_url = params["redirect_uri"]
        separator = "&" if "?" in redirect_url else "?"
        query = {"code": code}
        if params.get("state"):
            query["state"] = params["state"]
        self.send_response(302)
        self.send_header("Location", f"{redirect_url}{separator}{urlencode(query)}")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _handle_oauth_token(self) -> None:
        if not self.server.oauth_enabled:
            self._send_oauth_error(404, "not_found", "OAuth is not enabled")
            return
        form = self._read_form_body()
        grant_type = form.get("grant_type")
        if grant_type == "authorization_code":
            self._exchange_authorization_code(form)
            return
        if grant_type == "refresh_token":
            self._exchange_refresh_token(form)
            return
        self._send_oauth_error(400, "unsupported_grant_type", "Unsupported grant_type")

    def _exchange_authorization_code(self, form: Dict[str, str]) -> None:
        code = form.get("code", "")
        record = self.server.oauth_authorization_codes.get(code)
        if not record or record["expires_at"] < time.time():
            self._send_oauth_error(400, "invalid_grant", "Invalid authorization code")
            return
        if form.get("client_id") != record["client_id"]:
            self._send_oauth_error(400, "invalid_grant", "client_id mismatch")
            return
        if form.get("redirect_uri") != record["redirect_uri"]:
            self._send_oauth_error(400, "invalid_grant", "redirect_uri mismatch")
            return
        if not self._pkce_matches(form.get("code_verifier", ""), record["code_challenge"]):
            self._send_oauth_error(400, "invalid_grant", "PKCE verification failed")
            return
        requested_resource = form.get("resource")
        if requested_resource and requested_resource != record["resource"]:
            self._send_oauth_error(400, "invalid_target", "resource mismatch")
            return
        self.server.oauth_authorization_codes.pop(code, None)
        self._send_json(
            200,
            self._issue_oauth_tokens(record["client_id"], record["scopes"], record["resource"]),
        )

    def _exchange_refresh_token(self, form: Dict[str, str]) -> None:
        refresh_token = form.get("refresh_token", "")
        record = self.server.oauth_refresh_tokens.get(refresh_token)
        if not record or record["expires_at"] < time.time():
            self.server.oauth_refresh_tokens.pop(refresh_token, None)
            self.server.save_oauth_state()
            self._send_oauth_error(400, "invalid_grant", "Invalid refresh token")
            return
        if form.get("client_id") != record["client_id"]:
            self._send_oauth_error(400, "invalid_grant", "client_id mismatch")
            return
        requested_resource = form.get("resource")
        if requested_resource and requested_resource != record["resource"]:
            self._send_oauth_error(400, "invalid_target", "resource mismatch")
            return
        self.server.oauth_refresh_tokens.pop(refresh_token, None)
        self._send_json(
            200,
            self._issue_oauth_tokens(record["client_id"], record["scopes"], record["resource"]),
        )

    def _issue_oauth_tokens(self, client_id: str, scopes: List[str], resource: str) -> Dict[str, Any]:
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        now = time.time()
        self.server.oauth_access_tokens[access_token] = {
            "client_id": client_id,
            "scopes": scopes,
            "resource": resource,
            "expires_at": now + self.server.oauth_access_token_ttl_seconds,
        }
        self.server.oauth_refresh_tokens[refresh_token] = {
            "client_id": client_id,
            "scopes": scopes,
            "resource": resource,
            "expires_at": now + self.server.oauth_refresh_token_ttl_seconds,
        }
        self.server.save_oauth_state()
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": self.server.oauth_access_token_ttl_seconds,
            "refresh_token": refresh_token,
            "scope": " ".join(scopes),
        }

    def _validate_authorization_params(self, params: Dict[str, str]) -> Optional[str]:
        if params.get("response_type") != "code":
            return "Unsupported response_type."
        client_id = params.get("client_id")
        client = self.server.oauth_clients.get(client_id or "")
        if not client:
            return "Unknown OAuth client."
        redirect_uri = params.get("redirect_uri")
        if not redirect_uri or redirect_uri not in client.get("redirect_uris", []):
            return "redirect_uri is not registered for this client."
        if not self._redirect_uri_allowed(redirect_uri):
            return "redirect_uri is not allowed for this server."
        if params.get("code_challenge_method") != "S256" or not params.get("code_challenge"):
            return "PKCE S256 code_challenge is required."
        resource = params.get("resource")
        if resource and resource != self._resource_url():
            return "OAuth resource does not match this Agent Decision Bridge endpoint."
        requested_scopes = self._requested_scopes(params.get("scope"))
        if not set(requested_scopes).issubset(set(self.server.oauth_scopes)):
            return "Requested scope is not supported."
        return None

    def _requested_scopes(self, scope_value: Optional[str]) -> List[str]:
        scopes = [scope for scope in (scope_value or "").split() if scope]
        return scopes or list(self.server.oauth_scopes)

    def _redirect_uri_allowed(self, value: str) -> bool:
        try:
            parsed = urlparse(value)
        except ValueError:
            return False
        host = parsed.hostname or ""
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        return host.lower() in self.server.oauth_allowed_redirect_hosts

    def _authorization_form_html(self, params: Dict[str, str], error: Optional[str] = None) -> str:
        hidden_fields = "\n".join(
            f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(value)}" />'
            for key, value in params.items()
            if key != "owner_token"
        )
        error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Connect {html.escape(self._resource_name())}</title>
    <style>
      body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }}
      main {{ max-width: 460px; margin: 12vh auto; padding: 32px; background: #111827; border: 1px solid #334155; border-radius: 18px; }}
      h1 {{ margin: 0 0 12px; font-size: 28px; }}
      p {{ line-height: 1.5; color: #cbd5e1; }}
      label {{ display: block; margin: 18px 0 8px; font-weight: 600; }}
      input {{ box-sizing: border-box; width: 100%; padding: 12px 14px; border-radius: 10px; border: 1px solid #475569; background: #020617; color: #e2e8f0; font-size: 16px; }}
      button {{ margin-top: 18px; width: 100%; border: 0; border-radius: 10px; padding: 12px 14px; font-weight: 700; color: #020617; background: #38bdf8; cursor: pointer; }}
      .error {{ color: #fecaca; background: #7f1d1d; border-radius: 10px; padding: 10px 12px; }}
      .warning {{ color: #fde68a; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Connect {html.escape(self._resource_name())}</h1>
      <p class="warning">{html.escape(self._authorization_warning())}</p>
      <p>{html.escape(self._authorization_description())}</p>
      {error_html}
      <form method="post">
        {hidden_fields}
        <label for="owner_token">Owner password</label>
        <input id="owner_token" name="owner_token" type="password" autocomplete="current-password" autofocus required />
        <button type="submit">Authorize {html.escape(self._resource_name())}</button>
      </form>
    </main>
  </body>
</html>"""

    def _authorization_warning(self) -> str:
        if self.server.connected_agent_enabled:
            return (
                "Risk 4/5-5/5: approve only if you intentionally want ChatGPT "
                "to connect to local project workspaces. Read/search are automatic. "
                "The bounded product helper may use one host-native confirmation for "
                "a previewed patch or immutable prepared action; raw write, edit, and "
                "bash retain server approval unless Danger Auto is explicitly enabled."
            )
        if self.server.full_agent_enabled:
            return (
                "Risk 5/5: approve only if you intentionally want ChatGPT to read, "
                "write, edit, search, and run shell commands in configured workspaces."
            )
        if self.server.mode == MODE_READ_ONLY_PROJECT:
            return (
                "Risk 3/5-4/5: approve only if you intentionally want ChatGPT "
                "to read and search protected project content. This connector "
                "cannot write files or run shell commands."
            )
        return (
            "Only approve this if you are intentionally connecting ChatGPT to this "
            "package-only Auto MCP Controlled Advisor connector."
        )

    def _authorization_description(self) -> str:
        if self.server.connected_agent_enabled:
            return (
                "Connected Agent mode is not a sandbox. It can list, read, glob, "
                "grep, write, edit, and request bash execution inside opened "
                "workspaces under configured allowed roots. Sensitive paths and "
                "unsafe commands are blocked by server policy."
            )
        if self.server.full_agent_enabled:
            return (
                "Full-Agent mode is not a sandbox. Shell commands run with the local "
                "user account inside opened workspaces under configured allowed roots."
            )
        if self.server.mode == MODE_READ_ONLY_PROJECT:
            return (
                "Read-Only Project Advisor mode can list, read, glob, and grep files "
                "inside configured allowed roots. Sensitive paths such as .env, .git, "
                "SSH keys, cloud credentials, certificates, and token files are blocked."
            )
        return (
            "This connector can read decision packages, submit advisor advice, and "
            "query task status. It cannot read real projects, run shell commands, "
            "inspect Git, install dependencies, request local fact checks, or "
            "authorize execution."
        )

    def _read_json_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Parse error: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Expected JSON object")
        return payload

    def _read_form_body(self) -> Dict[str, str]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(length).decode("utf-8")
        return {key: values[-1] for key, values in parse_qs(body).items()}

    def _pkce_matches(self, verifier: str, challenge: str) -> bool:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        computed = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return self._safe_equals(computed, challenge)

    def _safe_equals(self, left: str, right: str) -> bool:
        left_bytes = left.encode("utf-8")
        right_bytes = right.encode("utf-8")
        if len(left_bytes) != len(right_bytes):
            return False
        return hmac.compare_digest(left_bytes, right_bytes)

    def _validate_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and origin not in self.server.allowed_origins:
            self._send_json_error(403, None, -32000, "Forbidden origin")
            return False
        return True

    def _validate_host(self) -> bool:
        if "*" in self.server.allowed_hosts:
            return True
        host = host_from_header(self.headers.get("Host"))
        if not host or host not in self.server.allowed_hosts:
            self._send_json_error(403, None, -32000, "Forbidden host")
            return False
        return True

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_oauth_error(self, status: int, error: str, description: str) -> None:
        self._send_json(
            status,
            {
                "error": error,
                "error_description": description,
            },
        )

    def _send_html(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_empty(self, status: int, headers: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json_error(
        self, status: int, request_id: Optional[Any], code: int, message: str
    ) -> None:
        self._send_json(
            status,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            },
        )

    def _send_plain(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _debug_jsonrpc(self, payload: Any, status: int) -> None:
        if os.environ.get("DECISION_INBOX_MCP_DEBUG") != "1":
            return
        method = payload.get("method") if isinstance(payload, dict) else type(payload).__name__
        print(f"debug jsonrpc_method={method!r} status={status}", file=sys.stderr)


def create_server(
    host: str,
    port: int,
    tasks_root: Path,
    auth_token: Optional[str],
    allowed_origins: Optional[List[str]] = None,
    public_base_url: Optional[str] = None,
    allowed_hosts: Optional[List[str]] = None,
    oauth_owner_token: Optional[str] = None,
    oauth_scopes: Optional[List[str]] = None,
    oauth_allowed_redirect_hosts: Optional[List[str]] = None,
    oauth_access_token_ttl_seconds: int = 3600,
    oauth_refresh_token_ttl_seconds: int = 2592000,
    oauth_state_file: Optional[Path] = None,
    session_activity_file: Optional[Path] = None,
    mode: str = MODE_AUTO_MCP,
    allowed_roots: Optional[List[Path]] = None,
    allowed_tasks: Optional[Dict[str, str]] = None,
    trust_host_confirmation_for_previewed_patches: bool = False,
    initial_permission_mode: str = PERMISSION_APPROVAL,
) -> DecisionInboxHTTPServer:
    normalized_mode = normalize_mode(mode)
    if normalized_mode in {MODE_MANUAL, MODE_ASK_FIRST}:
        raise ValueError("Ask First mode does not start the HTTP MCP server")
    store = DecisionInboxStore(tasks_root)
    normalized_public_base_url = normalize_public_base_url(public_base_url)
    if normalized_mode == MODE_FULL_AGENT:
        workspace_profile = PROFILE_FULL_AGENT
    elif normalized_mode == MODE_CONNECTED_AGENT:
        workspace_profile = PROFILE_CONNECTED_AGENT
    elif normalized_mode == MODE_READ_ONLY_PROJECT:
        workspace_profile = PROFILE_READ_ONLY_PROJECT
    else:
        workspace_profile = None
    full_agent_manager = (
        FullAgentWorkspaceManager(
            allowed_roots or [],
            profile=workspace_profile,
            allowed_tasks=allowed_tasks,
            trust_host_confirmation_for_previewed_patches=(
                trust_host_confirmation_for_previewed_patches
            ),
            initial_permission_mode=initial_permission_mode,
        )
        if workspace_profile
        else None
    )
    server = DecisionInboxHTTPServer(
        (host, port),
        DecisionInboxMCPHandler,
        store=store,
        auth_token=auth_token,
        allowed_origins=allowed_origins or DEFAULT_ALLOWED_ORIGINS,
        allowed_hosts=derive_allowed_hosts(host, normalized_public_base_url, allowed_hosts),
        public_base_url=normalized_public_base_url,
        oauth_owner_token=oauth_owner_token.strip() if oauth_owner_token else None,
        oauth_scopes=oauth_scopes or default_oauth_scopes(normalized_mode),
        oauth_allowed_redirect_hosts=set(
            host_from_header(value)
            for value in (
                oauth_allowed_redirect_hosts
                or ["chatgpt.com", "localhost", "127.0.0.1"]
            )
            if host_from_header(value)
        ),
        oauth_access_token_ttl_seconds=oauth_access_token_ttl_seconds,
        oauth_refresh_token_ttl_seconds=oauth_refresh_token_ttl_seconds,
        oauth_state_file=oauth_state_file,
        session_activity_file=session_activity_file,
        mode=normalized_mode,
        full_agent_manager=full_agent_manager,
    )
    if (
        normalized_mode in {MODE_READ_ONLY_PROJECT, MODE_FULL_AGENT, MODE_CONNECTED_AGENT}
        and server.oauth_state_file
    ):
        server.save_oauth_state()
    return server


def normalize_mode(value: Optional[str]) -> str:
    mode = (value or MODE_AUTO_MCP).strip()
    if mode not in VALID_MODES:
        raise ValueError(f"Mode must be one of: {', '.join(sorted(VALID_MODES))}")
    return mode


def default_oauth_scopes(mode: str) -> List[str]:
    if mode == MODE_CONNECTED_AGENT:
        return ["connected-agent"]
    if mode == MODE_FULL_AGENT:
        return ["full-agent"]
    if mode == MODE_READ_ONLY_PROJECT:
        return ["read-only-project"]
    return ["decision-inbox"]


def normalize_public_base_url(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    public_base_url = value.strip().rstrip("/")
    if not public_base_url:
        return None
    parsed = urlparse(public_base_url)
    if parsed.scheme != "https":
        raise ValueError("Public base URL must use https")
    if not parsed.netloc:
        raise ValueError("Public base URL must include a hostname")
    if parsed.path not in ("", "/"):
        raise ValueError("Public base URL must be the origin only, without /mcp")
    if parsed.query or parsed.fragment:
        raise ValueError("Public base URL must not include query strings or fragments")
    return f"{parsed.scheme}://{parsed.netloc}"


def public_mcp_url(public_base_url: Optional[str]) -> Optional[str]:
    normalized = normalize_public_base_url(public_base_url)
    if normalized is None:
        return None
    return f"{normalized}/mcp"


def derive_allowed_hosts(
    bind_host: str,
    public_base_url: Optional[str],
    extra_hosts: Optional[List[str]] = None,
) -> Set[str]:
    hosts = {"localhost", "127.0.0.1", "::1"}
    if bind_host not in ("", "0.0.0.0", "::"):
        hosts.add(bind_host.lower())
    if public_base_url:
        hostname = urlparse(public_base_url).hostname
        if hostname:
            hosts.add(hostname.lower())
    for host in extra_hosts or []:
        normalized = host_from_header(host)
        if normalized:
            hosts.add(normalized)
    return hosts


def host_from_header(value: Optional[str]) -> str:
    if not value:
        return ""
    host = value.strip().lower()
    if host == "*":
        return "*"
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end != -1 else host.strip("[]")
    if host.count(":") == 1:
        return host.rsplit(":", 1)[0]
    return host


def parse_string_list(value: Optional[str], default: Optional[List[str]] = None) -> List[str]:
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_path_list(value: Optional[str]) -> List[Path]:
    return [Path(item).expanduser() for item in parse_string_list(value)]


def parse_positive_int(value: Optional[str], default: int, name: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def read_optional_secret_file(value: Optional[str], name: str) -> Optional[str]:
    if not value:
        return None
    path = Path(value).expanduser()
    try:
        secret = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"{name} could not be read: {exc}") from exc
    return secret or None


def parse_optional_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    if value.strip().lower() == "none":
        return None
    return Path(value).expanduser()


def resolve_oauth_state_file(mode: str, value: Optional[str]) -> Optional[Path]:
    if value and value.strip().lower() == "none":
        return None
    if value:
        return Path(value).expanduser()
    if mode in {MODE_READ_ONLY_PROJECT, MODE_FULL_AGENT, MODE_CONNECTED_AGENT}:
        return DEFAULT_FULL_AGENT_STATE_FILE
    return None


def resolve_owner_token(
    mode: str,
    token: Optional[str],
    token_file: Optional[str],
) -> tuple[Optional[str], Optional[Path], bool]:
    if token:
        return token.strip(), None, False
    if token_file:
        path = Path(token_file).expanduser()
        return read_optional_secret_file(str(path), "DECISION_INBOX_OAUTH_OWNER_TOKEN_FILE"), path, False
    if mode not in {MODE_READ_ONLY_PROJECT, MODE_FULL_AGENT, MODE_CONNECTED_AGENT}:
        return None, None, False
    path = DEFAULT_FULL_AGENT_OWNER_TOKEN_FILE
    if path.is_file():
        return read_optional_secret_file(str(path), "FULL_AGENT_OAUTH_OWNER_TOKEN_FILE"), path, False
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(32)
    path.write_text(f"{generated}\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return generated, path, True


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Decision Inbox MCP v1 server over Streamable HTTP."
    )
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default=os.environ.get("AGENT_BRIDGE_MODE", MODE_AUTO_MCP),
        help="Run mode. Defaults to auto-mcp.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--tasks-root", type=Path, default=default_tasks_root())
    parser.add_argument(
        "--auth-token",
        help="Optional bearer token required in Authorization header.",
    )
    parser.add_argument(
        "--allowed-root",
        type=Path,
        action="append",
        dest="allowed_roots",
        help=(
            "Allowed project root for connected-agent, read-only-project, or "
            "full-agent mode. Can be passed multiple times."
        ),
    )
    parser.add_argument(
        "--allowed-task",
        action="append",
        default=[],
        metavar="NAME=COMMAND",
        help=(
            "Exact local task exposed through list_tasks/run_task in Connected Agent. "
            "Can be passed multiple times."
        ),
    )
    parser.add_argument(
        "--trust-host-confirmation-for-previewed-patches",
        action="store_true",
        help=(
            "Use the MCP host's native write confirmation as the sole approval for "
            "single-use preview_patch/apply_patch and prepare_action/commit_action "
            "commits. Intended for the bounded ChatGPT Connected Agent helper."
        ),
    )
    parser.add_argument(
        "--initial-permission-mode",
        choices=[PERMISSION_APPROVAL, PERMISSION_CONTROLLED_AUTO],
        default=PERMISSION_APPROVAL,
        help=(
            "Initial Connected Agent permission mode. Direct starts default to the "
            "hidden approval fallback; the product helper passes controlled_auto."
        ),
    )
    parser.add_argument(
        "--allow-origin",
        action="append",
        dest="allowed_origins",
        help="Allowed Origin header. Can be passed multiple times.",
    )
    parser.add_argument(
        "--public-base-url",
        default=os.environ.get("DECISION_INBOX_PUBLIC_BASE_URL"),
        help="Optional public HTTPS origin for tunnel/reverse-proxy use, without /mcp.",
    )
    parser.add_argument(
        "--allow-host",
        action="append",
        dest="allowed_hosts",
        help="Allowed Host header. Derived from local host and public base URL by default.",
    )
    parser.add_argument(
        "--oauth-owner-token",
        default=os.environ.get("DECISION_INBOX_OAUTH_OWNER_TOKEN"),
        help="Optional Owner password that enables OAuth authorization-code auth.",
    )
    parser.add_argument(
        "--oauth-owner-token-file",
        default=os.environ.get("DECISION_INBOX_OAUTH_OWNER_TOKEN_FILE"),
        help=(
            "Optional file containing the OAuth Owner password. "
            "Used only when --oauth-owner-token is not set."
        ),
    )
    parser.add_argument(
        "--oauth-scopes",
        default=os.environ.get("DECISION_INBOX_OAUTH_SCOPES"),
        help="Comma-separated OAuth scopes. Defaults to the selected mode's scope.",
    )
    parser.add_argument(
        "--oauth-allowed-redirect-host",
        action="append",
        dest="oauth_allowed_redirect_hosts",
        help=(
            "Allowed OAuth redirect hostname. Can be passed multiple times. "
            "Defaults to chatgpt.com, localhost, and 127.0.0.1."
        ),
    )
    parser.add_argument(
        "--oauth-access-token-ttl-seconds",
        default=os.environ.get("DECISION_INBOX_OAUTH_ACCESS_TOKEN_TTL_SECONDS"),
        help="OAuth access-token TTL in seconds. Defaults to 3600.",
    )
    parser.add_argument(
        "--oauth-refresh-token-ttl-seconds",
        default=os.environ.get("DECISION_INBOX_OAUTH_REFRESH_TOKEN_TTL_SECONDS"),
        help="OAuth refresh-token TTL in seconds. Defaults to 2592000.",
    )
    parser.add_argument(
        "--oauth-state-file",
        default=os.environ.get("DECISION_INBOX_OAUTH_STATE_FILE"),
        help=(
            "Optional JSON file for persistent OAuth client/access/refresh token state. "
            "Disabled unless explicitly set."
        ),
    )
    parser.add_argument(
        "--session-activity-file",
        type=Path,
        default=(
            Path(os.environ["AGENT_BRIDGE_SESSION_ACTIVITY_FILE"]).expanduser()
            if os.environ.get("AGENT_BRIDGE_SESSION_ACTIVITY_FILE")
            else None
        ),
        help=(
            "Optional Connected Agent/Full-Agent/read-only-project session state file whose "
            "last_activity should be refreshed on authenticated MCP requests."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    mode = normalize_mode(args.mode)
    if mode in {MODE_MANUAL, MODE_ASK_FIRST}:
        print("Agent Decision Bridge Ask First mode: use decision-inbox package/advice files.")
        print("No HTTP MCP server was started.")
        return 0
    oauth_owner_token, owner_token_file, owner_token_created = resolve_owner_token(
        mode,
        args.oauth_owner_token,
        args.oauth_owner_token_file,
    )
    oauth_state_file = resolve_oauth_state_file(mode, args.oauth_state_file)
    server = create_server(
        host=args.host,
        port=args.port,
        tasks_root=args.tasks_root,
        auth_token=args.auth_token or os.environ.get("DECISION_INBOX_MCP_TOKEN"),
        allowed_origins=args.allowed_origins,
        public_base_url=args.public_base_url,
        allowed_hosts=args.allowed_hosts,
        oauth_owner_token=oauth_owner_token,
        oauth_scopes=parse_string_list(args.oauth_scopes, default_oauth_scopes(mode)),
        oauth_allowed_redirect_hosts=args.oauth_allowed_redirect_hosts
        or parse_string_list(os.environ.get("DECISION_INBOX_OAUTH_ALLOWED_REDIRECT_HOSTS")),
        oauth_access_token_ttl_seconds=parse_positive_int(
            args.oauth_access_token_ttl_seconds,
            3600,
            "DECISION_INBOX_OAUTH_ACCESS_TOKEN_TTL_SECONDS",
        ),
        oauth_refresh_token_ttl_seconds=parse_positive_int(
            args.oauth_refresh_token_ttl_seconds,
            2592000,
            "DECISION_INBOX_OAUTH_REFRESH_TOKEN_TTL_SECONDS",
        ),
        oauth_state_file=oauth_state_file,
        session_activity_file=args.session_activity_file,
        mode=mode,
        allowed_roots=args.allowed_roots
        or parse_path_list(os.environ.get("AGENT_BRIDGE_ALLOWED_ROOTS")),
        allowed_tasks=parse_allowed_tasks(args.allowed_task),
        trust_host_confirmation_for_previewed_patches=(
            args.trust_host_confirmation_for_previewed_patches
        ),
        initial_permission_mode=args.initial_permission_mode,
    )
    print(f"Agent Decision Bridge MCP HTTP server listening on http://{args.host}:{args.port}/mcp")
    print(f"Mode: {server.mode}")
    if server.public_base_url:
        print(f"Public MCP URL: {public_mcp_url(server.public_base_url)}")
    print(f"Allowed hosts: {', '.join(sorted(server.allowed_hosts))}")
    print(f"OAuth owner-password flow: {'enabled' if server.oauth_enabled else 'disabled'}")
    if owner_token_file:
        created_text = "generated" if owner_token_created else "configured"
        print(f"OAuth owner-password file: {created_text} path={owner_token_file}")
        print(f"View Owner password with: cat {owner_token_file}")
    if server.oauth_state_file:
        print(f"OAuth state persistence: enabled path={server.oauth_state_file}")
    else:
        print("OAuth state persistence: disabled")
    if server.mode == MODE_READ_ONLY_PROJECT and server.full_agent_manager:
        print("Risk coefficient: 3/5-4/5")
        print(
            "Risk reason: read-only-project exposes protected project listing, "
            "file reads, read_lines, glob, and grep to the connected MCP client."
        )
        print(
            "Allowed roots: "
            + ", ".join(str(root) for root in server.full_agent_manager.allowed_roots)
        )
    if server.mode == MODE_CONNECTED_AGENT and server.full_agent_manager:
        print(f"Risk coefficient: {server.full_agent_manager.risk_level}")
        print(
            "Risk reason: connected-agent exposes local project read/search; the product "
            "helper starts in Controlled Auto for previewed patches, immutable prepared "
            "actions, and owner-configured tasks; raw write/edit/bash are legacy "
            "approval-gated compatibility tools."
        )
        print("Danger Auto phrase: dangerously trust connected agent")
        print(
            "Allowed roots: "
            + ", ".join(str(root) for root in server.full_agent_manager.allowed_roots)
        )
    if server.full_agent_enabled and server.full_agent_manager:
        print("Risk coefficient: 5/5")
        print(
            "Risk reason: full-agent exposes local file read/write/edit/search "
            "and shell execution to the connected MCP client."
        )
        print(
            "Allowed roots: "
            + ", ".join(str(root) for root in server.full_agent_manager.allowed_roots)
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
