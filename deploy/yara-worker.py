"""Trusted one-shot classic YARA worker. Inputs are data; includes are disabled."""

import contextlib
import json
import os
from pathlib import Path
import re
import sys


def diagnostic(message, severity="error"):
    match = re.search(r"line (\d+)", message)
    return dict(
        severity=severity,
        message=message[:4000],
        line=int(match[1]) if match else 1,
        column=None,
        origin="compiler",
    )


def main():
    try:
        import yara
    except ImportError:
        print(
            json.dumps(
                dict(
                    available=False,
                    message="Install requirements-yara.txt in the administrator-configured Python environment.",
                )
            )
        )
        return
    if sys.argv[1:] == ["--version"]:
        print(
            json.dumps(
                dict(
                    available=yara.__version__ == "4.5.4"
                    and yara.YARA_VERSION == "4.5.4",
                    version=yara.YARA_VERSION,
                    binding=yara.__version__,
                    message=(
                        "Classic YARA 4.5.4 ready; includes are disabled."
                        if yara.__version__ == "4.5.4" and yara.YARA_VERSION == "4.5.4"
                        else "Classic YARA 4.5.4 required; YARA-X is a separate engine."
                    ),
                )
            )
        )
        return
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (10, 11))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    # macOS does not reliably implement RLIMIT_AS; the parent still bounds time/output.
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = dict(compiled=False, diagnostics=[], results=[], version=yara.__version__)
    protocol = os.dup(1)
    os.dup2(2, 1)
    try:
        if yara.__version__ != "4.5.4" or yara.YARA_VERSION != "4.5.4":
            raise ValueError("Classic YARA 4.5.4 is required.")
        source = Path("source.yara").read_bytes().decode("utf-8-sig")
        # Redirect module console messages away from the JSON protocol.
        with contextlib.redirect_stdout(sys.stderr):
            rules = yara.compile(source=source, includes=False)
            result["compiled"] = True
            for warning in getattr(rules, "warnings", [])[:100]:
                result["diagnostics"].append(diagnostic(str(warning), "warning"))
            for name in ("positive", "baseline"):
                sample = Path(name + ".sample")
                if not sample.exists():
                    continue
                entry = dict(sample=name, status="scanning", matches=[])
                result["results"].append(entry)
                try:

                    def matched(data):
                        if data["matches"]:
                            strings = []
                            for item in data["strings"]:
                                for instance in item.instances:
                                    if len(strings) < 100:
                                        strings.append(
                                            dict(
                                                identifier=item.identifier,
                                                offset=instance.offset,
                                                length=instance.matched_length,
                                                preview=instance.matched_data[
                                                    :32
                                                ].hex(),
                                            )
                                        )
                            if len(entry["matches"]) >= 100:
                                raise ValueError(
                                    "Match reporting limit (100 rules) exceeded."
                                )
                            entry["matches"].append(
                                dict(rule=data["rule"], strings=strings)
                            )
                        return yara.CALLBACK_CONTINUE

                    rules.match(
                        data=sample.read_bytes(),
                        timeout=5,
                        callback=matched,
                        which_callbacks=yara.CALLBACK_MATCHES,
                    )
                    entry["status"] = "match" if entry["matches"] else "no match"
                except Exception as error:
                    entry.update(status="error", error=str(error)[:2000])
    except Exception as error:
        result["diagnostics"].append(diagnostic(str(error)))
    finally:
        os.dup2(protocol, 1)
        os.close(protocol)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
