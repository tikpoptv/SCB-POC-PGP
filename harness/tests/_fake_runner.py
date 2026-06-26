"""A tiny fake Runner used by the SubprocessDriver unit tests."""

import json
import os
import sys
import time


def main() -> int:
    raw = sys.stdin.read()

    sleep = float(os.environ.get("FAKE_SLEEP", "0"))
    if sleep > 0:
        time.sleep(sleep)

    stderr_text = os.environ.get("FAKE_STDERR", "")
    if stderr_text:
        sys.stderr.write(stderr_text)
        sys.stderr.flush()

    exit_code = int(os.environ.get("FAKE_EXIT_CODE", "0"))
    mode = os.environ.get("FAKE_STDOUT_MODE", "valid")

    if mode == "empty":
        return exit_code
    if mode == "garbage":
        sys.stdout.write("this is not json {")
        return exit_code

    default_chk = "sha256:" + "ab" * 32
    variant = "go-stream-parallel"
    concurrency = 1
    output_encoding = "binary"
    mode_field = "steady_state"
    key_chk = default_chk
    cor_chk = default_chk
    try:
        cmd = json.loads(raw)
        variant = cmd.get("variantId", variant)
        concurrency = cmd.get("concurrency", concurrency)
        output_encoding = cmd.get("outputEncoding", output_encoding)
        mode_field = cmd.get("mode", mode_field)
        key_chk = cmd.get("keySetChecksum", key_chk)
        cor_chk = cmd.get("corpusChecksum", cor_chk)
    except Exception:
        pass

    out = {
        "runnerId": "go",
        "variantId": variant,
        "mode": mode_field,
        "scenarioId": "s1",
        "cryptoProfileId": "p1",
        "concurrency": concurrency,
        "outputEncoding": output_encoding,
        "hardwareAccel": True,
        "keySetChecksumSeen": key_chk,
        "corpusChecksumSeen": cor_chk,
        "operations": [],
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
