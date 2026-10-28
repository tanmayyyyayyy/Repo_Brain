import os
import pytest
from repobrain import audit, cli

# ───── Audit: anchor-file verification via CLI
def test_audit_anchor_file_cli(tmp_path):
    home = str(tmp_path / "home")
    anchor_file = str(tmp_path / "anchor.txt")
    log = audit.AuditLog(home)
    log.append("test_event", "actor1", "ALLOWED", "detail 1")
    log.append("test_event", "actor2", "ALLOWED", "detail 2")

    # Step 1: Write anchor using --write-anchor
    rc = cli.main(["--home", home, "audit", "--write-anchor", anchor_file])
    assert rc == 0
    assert os.path.isfile(anchor_file)
    anchored_head = open(anchor_file).read().strip()
    assert len(anchored_head) == 64

    # Step 2: Verify against anchor file (should succeed)
    rc = cli.main(["--home", home, "audit", "--anchor-file", anchor_file])
    assert rc == 0

    # Step 3: Tamper with log by truncating or changing entries
    lines = open(log.path).read().splitlines()
    open(log.path, "w").write(lines[0] + "\n")  # delete second entry

    # Step 4: Verify against anchor file (should detect mismatch)
    rc = cli.main(["--home", home, "audit", "--anchor-file", anchor_file])
    assert rc == 1
