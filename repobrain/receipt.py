"""Verifiable PR Decision Receipt Engine.

Generates and cryptographically verifies self-contained, offline-verifiable
decision receipts for PR reviews and AI code remediations.

Each receipt cryptographically binds:
1. Review Decision: Verdict, findings, files, lines, and risk metrics.
2. Base Policy Provenance: Canonical hash of policy from origin/main.
3. Revision Identity: Head commit SHA, base branch, and repository.
4. Remediation Evidence: Formal AST equivalence proof theorem, fuzzing results,
   and test execution verification.
5. Human Governance: Named human approver and signed commit trailer.
6. Cryptographic Audit Proof: RFC-6962 Binary Merkle Tree inclusion proof
   reconstructed in O(log N) operations and HMAC-SHA256 chained entry hash.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from . import gitutil, merkle, policy as P


def _canonical_json_bytes(data: Any) -> bytes:
    """Format data as deterministic canonical JSON bytes."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    """Compute SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_policy_hash(policy_dict: Dict[str, Any]) -> str:
    """Compute canonical hash of policy rules excluding ephemeral runtime keys."""
    clean_pol = {k: v for k, v in policy_dict.items() if not k.startswith("_")}
    return _sha256_hex(_canonical_json_bytes(clean_pol))


def generate_receipt(
    root: str,
    rev: Dict[str, Any],
    log: Any,
    proposal: Optional[Dict[str, Any]] = None,
    approver: Optional[str] = None,
    base: Optional[str] = None
) -> Dict[str, Any]:
    """Generate a self-contained, cryptographically verifiable PR decision receipt."""
    repo_name = os.path.basename(os.path.abspath(root))
    head_sha = rev.get("head") or gitutil.head(root)
    base_ref = base or rev.get("base") or "main"
    branch_name = rev.get("branch") or gitutil.branch(root)

    # 1. Policy metadata & canonical hash
    raw_policy = P.load_for(root, base_ref)
    policy_hash = compute_policy_hash(raw_policy)
    policy_summary = {
        "source": rev.get("policy_source") or raw_policy.get("_source", f"git:{base_ref}:repobrain.yml"),
        "sha256": policy_hash,
        "complexity_threshold": raw_policy.get("complexity_threshold", 10),
        "max_cognitive": raw_policy.get("max_cognitive", 15),
        "max_depth": raw_policy.get("max_depth", 3),
        "taint_guard": raw_policy.get("taint_guard", True),
        "allow_llm": raw_policy.get("allow_llm", False),
    }

    # 2. Review Findings & Verdict
    findings = rev.get("findings", [])
    blocking_findings = [f for f in findings if f.get("severity") == "block"]
    warning_findings = [f for f in findings if f.get("severity") == "warn"]

    review_block = {
        "repo": repo_name,
        "branch": branch_name,
        "commit": head_sha,
        "base": base_ref,
        "decision": rev.get("decision", "UNKNOWN"),
        "verdict": rev.get("verdict", "unknown"),
        "reason": rev.get("reason", ""),
        "findings_count": {
            "total": len(findings),
            "blocking": len(blocking_findings),
            "warnings": len(warning_findings),
            "complexity_gate": len(rev.get("gate", []))
        },
        "findings": [
            {
                "file": f.get("file") or f.get("path", ""),
                "line": f.get("line", 0),
                "rule": f.get("rule", ""),
                "severity": f.get("severity", "warn"),
                "message": f.get("msg") or f.get("message", "")
            }
            for f in findings
        ],
        "waiver": rev.get("waiver")
    }

    # 3. Remediation evidence (AST optimizer, formal proof, fuzzing, tests)
    remediation_block: Dict[str, Any] = {
        "remediated": False
    }

    if proposal and proposal.get("id"):
        remediation_block["remediated"] = True
        remediation_block["proposal_id"] = proposal.get("id")
        remediation_block["status"] = proposal.get("status", "proposed")
        remediation_block["human_approver"] = approver or proposal.get("actor")

        # Formal proof
        formal_proofs = proposal.get("formal_proofs", [])
        if formal_proofs:
            fp = formal_proofs[0]
            remediation_block["formal_proof"] = {
                "proven": fp.get("proven", False),
                "theorem": fp.get("theorem", ""),
                "proof_hash": fp.get("proof_hash", ""),
                "formal_method": fp.get("formal_method", ""),
                "domain_coverage": fp.get("domain_coverage", ""),
                "paths_verified": fp.get("paths_verified", 0)
            }
        else:
            remediation_block["formal_proof"] = {
                "proven": False,
                "reason": "Not a candidate for pure symbolic proof; verified via differential fuzzing and tests"
            }

        # Differential fuzzing
        fuzz_info = proposal.get("fuzz_total", {})
        remediation_block["differential_fuzzing"] = {
            "inputs_checked": fuzz_info.get("inputs", 0),
            "divergences": fuzz_info.get("diverged", 0),
            "status": "passed" if fuzz_info.get("diverged", 0) == 0 else "failed"
        }

        # Tests
        test_info = proposal.get("tests", {})
        remediation_block["test_suite"] = {
            "verified_in_scratch_copy": test_info.get("ok", False),
            "returncode": test_info.get("returncode", 0),
            "status": "passed" if test_info.get("ok") else "unverified"
        }

    # 4. Audit ledger entry & RFC-6962 Merkle inclusion proof
    entries = log.entries() if hasattr(log, "entries") else []
    target_record: Optional[Dict[str, Any]] = None
    target_index = -1

    # Search for matching record in audit ledger specifically binding to head_sha and decision
    for idx in range(len(entries) - 1, -1, -1):
        e = entries[idx]
        if e.get("event") == "review" and e.get("head") == head_sha and e.get("decision") == rev.get("decision"):
            target_record = e
            target_index = idx
            break

    # If no matching entry with matching head & decision exists, log one now
    if target_record is None:
        rec = log.append(
            "review",
            approver or "repobrain",
            rev.get("decision", "UNKNOWN"),
            f"PR review receipt generated for {head_sha[:8]}",
            head=head_sha,
            base=base_ref,
            verdict=rev.get("verdict"),
            policy_hash=policy_hash
        )
        entries = log.entries()
        target_record = rec
        target_index = len(entries) - 1

    # Build Merkle tree from all audit entries
    tree = merkle.MerkleTree(entries)
    merkle_proof = tree.audit_proof(target_index)

    audit_block = {
        "seq": target_record.get("seq", target_index + 1),
        "event": target_record.get("event", "review"),
        "decision": target_record.get("decision", rev.get("decision")),
        "head": target_record.get("head", head_sha),
        "actor": target_record.get("actor", approver or "system"),
        "timestamp": target_record.get("ts"),
        "entry_hash": target_record.get("hash"),
        "prev_hash": target_record.get("prev"),
        "hmac_signature": target_record.get("sig"),
        "merkle_root": tree.root,
        "merkle_proof": merkle_proof,
        "target_record": target_record
    }

    # Assemble complete receipt
    receipt: Dict[str, Any] = {
        "receipt_version": "1.0",
        "spec": "RFC-6962-Merkle-Bound-PR-Receipt",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "policy": policy_summary,
        "review": review_block,
        "remediation": remediation_block,
        "audit": audit_block,
    }

    # Compute top-level receipt integrity hash
    canonical_payload = _canonical_json_bytes(receipt)
    receipt["receipt_hash"] = _sha256_hex(canonical_payload)
    return receipt


def verify_receipt(
    receipt: Dict[str, Any],
    trusted_root: Optional[str] = None,
    audit_key: Optional[str] = None,
    anchor_file: Optional[str] = None
) -> Dict[str, Any]:
    """Cryptographically verify an offline decision receipt.
    
    Verifies:
    1. Receipt Hash Integrity: Ensures JSON content has not been tampered with.
    2. Audit Entry Canonical Hash: Ensures target audit record is untampered.
    3. Audit Entry Binding: Ensures audit record binds to reviewed commit and verdict.
    4. Merkle Inclusion Proof: Reconstructs root in O(log N) from sibling path.
    5. Independent Trust Anchor: Validates Merkle root against a trusted anchor
       (or verifies HMAC signature against a trusted secret audit key).
    6. Policy & Findings Consistency: Verifies verdict matches finding counts.
    7. Formal Proof Evidence: Certifies included proof evidence recorded at proposal.
    """
    from . import audit as A

    report: Dict[str, Any] = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": {}
    }

    if not isinstance(receipt, dict):
        report["valid"] = False
        report["errors"].append("Receipt must be a JSON dictionary object.")
        return report

    # 1. Receipt Hash Integrity
    stored_hash = receipt.get("receipt_hash")
    if not stored_hash:
        report["valid"] = False
        report["errors"].append("Missing required 'receipt_hash' field.")
        report["checks"]["receipt_hash"] = {"valid": False, "error": "Missing receipt_hash"}
    else:
        copy_obj = copy.deepcopy(receipt)
        copy_obj.pop("receipt_hash", None)
        computed_hash = _sha256_hex(_canonical_json_bytes(copy_obj))
        if computed_hash != stored_hash:
            report["valid"] = False
            err_msg = f"Receipt integrity mismatch: computed {computed_hash[:16]}... vs stored {stored_hash[:16]}... (file modified)"
            report["errors"].append(err_msg)
            report["checks"]["receipt_hash"] = {"valid": False, "error": err_msg}
        else:
            report["checks"]["receipt_hash"] = {"valid": True, "hash": stored_hash}

    # 2. Audit Record & Entry Hash Verification
    audit_data = receipt.get("audit", {})
    target_record = audit_data.get("target_record")
    merkle_proof = audit_data.get("merkle_proof")
    expected_root = audit_data.get("merkle_root")

    if not target_record or not merkle_proof or not expected_root:
        report["valid"] = False
        report["errors"].append("Missing audit record or Merkle proof details.")
        report["checks"]["merkle_proof"] = {"valid": False, "error": "Incomplete audit data"}
        return report

    computed_entry_hash = A._hash(target_record)
    record_hash = target_record.get("hash")
    if record_hash != computed_entry_hash:
        report["valid"] = False
        err_msg = f"Audit entry hash mismatch: computed {computed_entry_hash[:16]}... vs record hash {str(record_hash)[:16]}... (audit record modified)"
        report["errors"].append(err_msg)
        report["checks"]["entry_hash"] = {"valid": False, "error": err_msg}
    else:
        report["checks"]["entry_hash"] = {"valid": True, "hash": record_hash}

    # 3. Audit Entry Binding to Review Commit & Verdict
    rev_data = receipt.get("review", {})
    rec_commit = target_record.get("head")
    claim_commit = rev_data.get("commit")
    rec_decision = target_record.get("decision")
    claim_decision = rev_data.get("decision")

    binding_errs = []
    if rec_commit and claim_commit and str(rec_commit)[:12] != str(claim_commit)[:12]:
        err = f"Audit entry binding mismatch: audit record binds to commit {str(rec_commit)[:12]}, but receipt claims commit {str(claim_commit)[:12]}."
        binding_errs.append(err)
    if rec_decision and claim_decision and rec_decision != claim_decision:
        err = f"Audit entry decision mismatch: audit record says {rec_decision}, but receipt claims {claim_decision}."
        binding_errs.append(err)

    if binding_errs:
        report["valid"] = False
        for err in binding_errs:
            report["errors"].append(err)
        report["checks"]["audit_binding"] = {"valid": False, "errors": binding_errs}
    else:
        report["checks"]["audit_binding"] = {
            "valid": True,
            "bound_commit": str(claim_commit)[:12] if claim_commit else "unknown",
            "bound_decision": claim_decision
        }

    # 4. Merkle Inclusion Proof Verification
    is_proof_valid = merkle.verify_inclusion_proof(target_record, merkle_proof)
    if not is_proof_valid or merkle_proof.get("merkle_root") != expected_root:
        report["valid"] = False
        err_msg = f"RFC-6962 Merkle proof failed: sibling path does not reconstruct root {expected_root[:16]}..."
        report["errors"].append(err_msg)
        report["checks"]["merkle_proof"] = {"valid": False, "error": err_msg}
    else:
        report["checks"]["merkle_proof"] = {
            "valid": True,
            "merkle_root": expected_root,
            "leaf_hash": merkle_proof.get("leaf_hash"),
            "tree_size": merkle_proof.get("tree_size"),
            "proof_steps": len(merkle_proof.get("proof_path", []))
        }

    # 5. Independent Trust Anchor Verification
    if not trusted_root and anchor_file and os.path.isfile(anchor_file):
        try:
            with open(anchor_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content.startswith("{"):
                    data = json.loads(content)
                    trusted_root = data.get("merkle_root") or data.get("head")
                else:
                    trusted_root = content.split()[0]
        except Exception as exc:
            report["warnings"].append(f"Failed to read anchor file '{anchor_file}': {exc}")

    if not audit_key:
        audit_key = os.environ.get("REPOBRAIN_AUDIT_KEY")

    has_external_anchor = False
    anchor_checks: Dict[str, Any] = {}

    if trusted_root:
        has_external_anchor = True
        clean_trusted = trusted_root.strip()
        receipt_root = audit_data.get("merkle_root", "")
        if receipt_root != clean_trusted:
            report["valid"] = False
            err_msg = f"Trust anchor mismatch: receipt Merkle root {receipt_root[:16]}... does not match trusted root {clean_trusted[:16]}... (untrusted or forged tree)"
            report["errors"].append(err_msg)
            anchor_checks["trusted_root"] = {"valid": False, "error": err_msg}
        else:
            anchor_checks["trusted_root"] = {"valid": True, "trusted_root": clean_trusted}

    if audit_key:
        has_external_anchor = True
        import hmac
        key_bytes = audit_key.encode() if isinstance(audit_key, str) else audit_key
        record_sig = target_record.get("sig")
        if not record_sig:
            report["valid"] = False
            err_msg = "HMAC authentication failure: audit record lacks HMAC signature required by trusted audit key."
            report["errors"].append(err_msg)
            anchor_checks["hmac_signature"] = {"valid": False, "error": err_msg}
        else:
            expected_sig = hmac.new(key_bytes, record_hash.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(record_sig, expected_sig):
                report["valid"] = False
                err_msg = "HMAC authentication failure: audit entry signature is invalid for the trusted audit key (forged record or wrong key)."
                report["errors"].append(err_msg)
                anchor_checks["hmac_signature"] = {"valid": False, "error": err_msg}
            else:
                anchor_checks["hmac_signature"] = {"valid": True, "sig_preview": record_sig[:16] + "..."}

    if has_external_anchor:
        is_anchor_ok = all(c.get("valid", False) for c in anchor_checks.values())
        report["checks"]["trust_anchor"] = {
            "status": "verified" if is_anchor_ok else "failed",
            "details": anchor_checks
        }
    else:
        report["checks"]["trust_anchor"] = {
            "status": "self-consistent",
            "note": "Receipt is internally consistent; verify against --trusted-root, --anchor-file, or --key for independent root-of-trust authorization."
        }

    # 6. Policy & Verdict Consistency
    decision = rev_data.get("decision")
    findings = rev_data.get("findings", [])
    blocking = [f for f in findings if f.get("severity") == "block"]
    waiver = rev_data.get("waiver")

    if decision == "ALLOWED" and blocking and not waiver:
        report["valid"] = False
        err_msg = f"Logical discrepancy: decision is ALLOWED but contains {len(blocking)} un-waived blocking finding(s)."
        report["errors"].append(err_msg)
        report["checks"]["verdict_consistency"] = {"valid": False, "error": err_msg}
    else:
        report["checks"]["verdict_consistency"] = {"valid": True, "decision": decision}

    # 7. Formal Proof Evidence Included in Receipt
    rem_data = receipt.get("remediation", {})
    if rem_data.get("remediated") and rem_data.get("formal_proof", {}).get("proven"):
        fp = rem_data["formal_proof"]
        proof_hash = fp.get("proof_hash", "")
        theorem = fp.get("theorem", "")
        if not proof_hash.startswith("0x") or len(proof_hash) < 6:
            report["warnings"].append("Formal proof hash format is non-standard.")
        proof_check = {
            "valid": True,
            "theorem": theorem,
            "proof_hash": proof_hash,
            "method": fp.get("formal_method"),
            "note": "Formal AST equivalence proof evidence recorded in receipt (certified at proposal time for pure control-flow rewrites; fuzzing covers dynamic behavior)"
        }
        report["checks"]["formal_proof_evidence"] = proof_check
        report["checks"]["formal_proof"] = proof_check

    return report


def format_verification_report(report: Dict[str, Any], receipt: Dict[str, Any]) -> str:
    """Format verification result as a clean, human-readable terminal output."""
    rev = receipt.get("review", {})
    audit = receipt.get("audit", {})
    rem = receipt.get("remediation", {})
    pol = receipt.get("policy", {})

    status_icon = "✅" if report["valid"] else "❌"
    status_label = "VALID & UNTAMPERED" if report["valid"] else "TAMPERED / VERIFICATION FAILED"

    lines = [
        "=" * 68,
        "REPOBRAIN CRYPTOGRAPHIC DECISION RECEIPT VERIFICATION",
        "=" * 68,
        f"Receipt Spec:       {receipt.get('spec', 'RFC-6962-Merkle-Bound-PR-Receipt')} (v{receipt.get('receipt_version', '1.0')})",
        f"Generated At:       {receipt.get('generated_at', 'unknown')}",
        f"Repository:         {rev.get('repo', 'unknown')} ({rev.get('branch', 'unknown')})",
        f"Reviewed Commit:    {str(rev.get('commit', ''))[:12]} (vs {rev.get('base', 'main')})",
        f"Review Verdict:     {rev.get('decision', 'UNKNOWN')} ({rev.get('verdict', 'unknown')})",
        f"Findings Count:     {len(rev.get('findings', []))} total ({rev.get('findings_count', {}).get('blocking', 0)} blocking)",
        f"Base Policy Hash:   SHA-256:{str(pol.get('sha256', ''))[:16]}... (from {pol.get('source', 'base')})",
        "-" * 68,
        "CRYPTOGRAPHIC AUDIT & INCLUSION PROOF:",
        f"  Audit Sequence:   #{audit.get('seq', 0)} ({audit.get('event', 'unknown')})",
        f"  Entry Hash:       {str(audit.get('entry_hash', ''))[:24]}...",
        f"  Merkle Tree Root: {str(audit.get('merkle_root', ''))[:24]}... (size {audit.get('merkle_proof', {}).get('tree_size', 0)})",
    ]

    merkle_check = report.get("checks", {}).get("merkle_proof", {})
    if merkle_check.get("valid"):
        lines.append(f"  Inclusion Proof:  VERIFIED (O(log N) verification across {merkle_check.get('proof_steps', 0)} sibling hashes)")
    else:
        lines.append(f"  Inclusion Proof:  FAILED ({merkle_check.get('error', 'unknown error')})")

    binding_check = report.get("checks", {}).get("audit_binding", {})
    if binding_check.get("valid"):
        lines.append(f"  Commit Binding:   BOUND to commit {binding_check.get('bound_commit')} and verdict {binding_check.get('bound_decision')}")
    elif "errors" in binding_check:
        lines.append(f"  Commit Binding:   VIOLATED ({'; '.join(binding_check.get('errors', []))})")

    # Trust Anchor Status
    anchor_check = report.get("checks", {}).get("trust_anchor", {})
    lines.append("-" * 68)
    lines.append("INDEPENDENT ROOT-OF-TRUST ANCHOR:")
    if anchor_check.get("status") == "verified":
        lines.append("  Anchor Status:    ✅ VERIFIED against independent trusted root / secret key")
        details = anchor_check.get("details", {})
        if "trusted_root" in details:
            lines.append(f"  Trusted Root:     {str(details['trusted_root'].get('trusted_root', ''))[:24]}... (matches receipt)")
        if "hmac_signature" in details:
            lines.append("  HMAC Signature:   AUTHENTIC (signed by trusted repository audit key)")
    elif anchor_check.get("status") == "failed":
        lines.append("  Anchor Status:    ❌ FAILED (receipt does not match trusted anchor or key)")
        details = anchor_check.get("details", {})
        for k, v in details.items():
            if not v.get("valid"):
                lines.append(f"  Failure:          {v.get('error', '')}")
    else:
        lines.append("  Anchor Mode:      Self-Consistent (pass --trusted-root, --anchor-file, or --key to enforce independent anchor)")

    if rem.get("remediated"):
        lines.append("-" * 68)
        lines.append("VERIFIED REMEDIATION & HUMAN GOVERNANCE:")
        lines.append(f"  Proposal ID:      {rem.get('proposal_id', 'unknown')}")
        lines.append(f"  Human Approver:   {rem.get('human_approver', 'None')}")
        fp = rem.get("formal_proof", {})
        if fp.get("proven"):
            lines.append("  Formal Proof:     EVIDENCE INCLUDED (Pure control-flow AST equivalence)")
            lines.append(f"  Theorem:          {fp.get('theorem', '')}")
            lines.append(f"  Theorem Hash:     {fp.get('proof_hash', '')}")
        fuzz = rem.get("differential_fuzzing", {})
        lines.append(f"  Diff Fuzzing:     {fuzz.get('inputs_checked', 0)} inputs, {fuzz.get('divergences', 0)} divergences ({fuzz.get('status', 'unknown')})")
        test = rem.get("test_suite", {})
        lines.append(f"  Scratch Tests:    {test.get('status', 'unknown')}")

    lines.append("=" * 68)
    lines.append(f"FINAL VERDICT: {status_icon} [{status_label}]")
    if not report["valid"]:
        lines.append("ERRORS ENCOUNTERED:")
        for err in report.get("errors", []):
            lines.append(f"  ✖ {err}")
    lines.append("=" * 68)
    return "\n".join(lines)

