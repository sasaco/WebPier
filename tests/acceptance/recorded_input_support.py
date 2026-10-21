"""The input an acceptance may have been recorded from (decision 72).

The real-runner acceptances recorded so far were made before the input had ``outputs``. The 出力項目 only choose which
reports a generation makes and are no condition of the calculation (ADR-0011), so such an acceptance still belongs to
current.json when everything but them is the recorded bytes. ``input_sha256s`` gives the SHA256 of the input as it is
(an acceptance recorded from now on) and without its last item ``outputs`` (one recorded before); the tests still
compare the files the engines are given.
"""

import re

from webpier.core.integrity import sha256

_OUTPUTS = re.compile(rb',(\r?\n)  "outputs": \{[^{}]*\}(?=\1\}\s*$)')


def input_sha256s(data: bytes) -> set[str]:
    """The SHA256 an acceptance of the input *data* may record: of it as it is, and as it was before the 出力項目."""
    stripped, count = _OUTPUTS.subn(b"", data)
    return {sha256(data), *((sha256(stripped),) if count == 1 else ())}
