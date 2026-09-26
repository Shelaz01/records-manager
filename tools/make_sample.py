"""Generate the sample admission form in ``samples/``.

    python tools/make_sample.py

The sample exists so anyone trying the scan flow has a form to open. It is
drawn from a test fixture and contains invented names and numbers only: a
real admission form carries a named patient's date of birth, address, next
of kin and diagnosis, and none of that belongs in a public repository.
"""
from __future__ import annotations

from pathlib import Path

from forms import render_fixture

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
FIXTURE = "typical_form"
TARGET = SAMPLES / "admission-form.png"


def main() -> None:
    path = render_fixture(FIXTURE, TARGET)
    print(f"wrote {path.relative_to(SAMPLES.parent)} from {FIXTURE}.txt")


if __name__ == "__main__":
    main()
