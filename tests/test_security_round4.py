import collections
import ipaddress
import os
import time
import pytest

from repobrain import server


def test_item1_client_ip_ignores_spoofed_xff_when_peer_not_trusted(monkeypatch):
    # Ensure trusted proxies is empty or does not include peer
    monkeypatch.setenv("REPOBRAIN_TRUSTED_PROXIES", "10.0.0.1")
    
    # Mock handler with untrusted socket peer 198.51.100.1
    class DummyHandler:
        client_address = ("198.51.100.1", 54321)
        headers = {"X-Forwarded-For": "203.0.113.99", "X-Real-IP": "203.0.113.99"}

    # Should ignore XFF and return the actual socket peer
    client_ip = server.resolve_client_ip(DummyHandler())
    assert client_ip == "198.51.100.1", f"Expected untrusted peer IP 198.51.100.1, got {client_ip}"


def test_item1_client_ip_resolves_rightmost_untrusted_from_trusted_proxy(monkeypatch):
    # Peer is a trusted reverse proxy
    monkeypatch.setenv("REPOBRAIN_TRUSTED_PROXIES", "10.0.0.0/8,172.16.0.0/12,127.0.0.1")

    class DummyHandler:
        client_address = ("10.0.0.2", 12345)
        # Client 203.0.113.50 went through intermediate proxy 172.16.1.1 then 10.0.0.2
        headers = {"X-Forwarded-For": "203.0.113.50, 172.16.1.1"}

    client_ip = server.resolve_client_ip(DummyHandler())
    assert client_ip == "203.0.113.50", f"Expected rightmost non-trusted IP 203.0.113.50, got {client_ip}"


def test_item1_rate_limiter_memory_is_bounded():
    limiter = server.BoundedRateLimiter(max_keys=10, window=60, max_attempts=5)
    for i in range(50):
        limiter.check(f"user_{i}")
    assert len(limiter) <= 10, f"Limiter memory exceeded max_keys: {len(limiter)}"


def test_item1_rate_limiter_enforces_separate_ip_and_email_limits():
    limiter = server.BoundedRateLimiter(max_keys=100, window=60, max_attempts=5)
    # 5 failed attempts from same IP
    for _ in range(5):
        assert limiter.check("ip:198.51.100.1") is True
    # 6th attempt from same IP blocked
    assert limiter.check("ip:198.51.100.1") is False

    # Different IP with same email: email key is checked separately
    for _ in range(5):
        assert limiter.check("email:target@company.internal") is True
    # 6th attempt for email blocked regardless of IP
    assert limiter.check("email:target@company.internal") is False
