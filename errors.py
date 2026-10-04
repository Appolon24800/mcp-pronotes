"""Stable error codes for MCP and HTTP-proxy clients."""


class ToolError(ValueError):
    def __init__(self, message, code="INVALID_ARGUMENT", relogin_required=False):
        super().__init__(message)
        self.code = code
        self.relogin_required = relogin_required


class AuthenticationRequired(ToolError):
    def __init__(self, message):
        super().__init__(message, "AUTHENTICATION_REQUIRED", relogin_required=True)
