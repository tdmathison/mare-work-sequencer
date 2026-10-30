"""Trusted image entrypoint; invoked ONLY inside the restricted worker container."""

import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import zipfile
from dataclasses import dataclass
from typing import Any
import httpx
from mws_sdk import MWSClient


@dataclass
class PluginContext:
    client: MWSClient
    artifact: str | None
    case_id: int | None
    inputs: dict[str, Any]
    configuration: dict[str, Any]
    dry_run: bool

    def log(self, message: str) -> None:
        print(
            json.dumps(
                {
                    "timestamp": time.time(),
                    "level": "info",
                    "message": str(message)[:8000],
                }
            ),
            flush=True,
            file=sys.stderr,
        )

    def external(self, service: str, path: str) -> Any:
        # Gateway holds connector credentials; they never enter the plugin.
        with httpx.Client(
            transport=httpx.HTTPTransport(uds="/gateway/api.sock"), trust_env=False
        ) as client:
            response = client.post(
                "http://worker/external", json={"service": service, "path": path}
            )
        response.raise_for_status()
        return response.json()


def prepare():
    os.chdir("/work")
    with zipfile.ZipFile("/snapshot/plugin.zip") as archive:
        archive.extractall(
            "/work"
        )  # Supervisor validated paths, types and bounded expansion.
    return json.loads(Path("/work/plugin.json").read_text())


def context():
    value = json.loads(Path("/snapshot/context.json").read_text())
    return PluginContext(
        MWSClient(
            base_url="http://worker",
            api_key="session",
            transport=httpx.HTTPTransport(uds="/gateway/api.sock"),
            trust_env=False,
            retries=0,
        ),
        value.get("artifact"),
        value.get("case_id"),
        value.get("inputs", {}),
        value.get("configuration", {}),
        False,
    )


def run():
    manifest = json.loads(Path("/work/plugin.json").read_text())
    path, name = manifest["entrypoint"].split(":")
    sys.path.insert(0, "/work")
    spec = importlib.util.spec_from_file_location(
        "mws_user_plugin", Path("/work") / path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctx = context()
    try:
        result = getattr(module, name)(ctx)
        import inspect, asyncio

        if inspect.isawaitable(result):
            result = asyncio.run(result)
        print(json.dumps({"result": result}, default=str), flush=True)
    finally:
        ctx.client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=["run"]
    )
    args = parser.parse_args()
    value = prepare()
    from packaging.requirements import Requirement

    for text in ["mws-sdk>=1,<2", *value.get("dependencies", [])]:
        req = Requirement(text)
        if importlib.metadata.version(req.name) not in req.specifier:
            raise ValueError("Worker image dependency incompatible: " + req.name)
    run()


if __name__ == "__main__":
    main()
