"""Jupyter Server Proxy configuration for AetherTerm.
This allows AetherTerm to be automatically discovered by jupyter-server-proxy.
"""


def setup_aetherterm():
    return {
        "command": [
            "aetherterm-agentserver",
            "--host",
            "127.0.0.1",
            "--port",
            "{port}",
            "--unsecure",
            "--uri-root-path",
            "/term",
        ],
        "timeout": 30,
        "launcher_entry": {
            "title": "AetherTerm",
            "icon_path": "/static/aetherterm.svg",
            "enabled": True,
        },
        "new_browser_tab": True,
    }
