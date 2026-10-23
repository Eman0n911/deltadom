import pytest
from deltadom.outcome import OutcomeCheck, OutcomeVerifier


def check(**overrides):
    return OutcomeCheck(**{"key": "amount", "scope": "article", "identity": "Invoice A",
                              "target": "input", "kind": "value", "expected": "100", **overrides})


async def test_reload_does_not_accept_unsaved_optimistic_change(live):
    page, _ = live
    html = '<article><h2>Invoice A</h2><input value="10"></article>'
    await page.route("http://outcome.test/", lambda route: route.fulfill(body=html, content_type="text/html"))
    await page.goto("http://outcome.test/")
    await page.locator("input").fill("100")
    verifier = OutcomeVerifier([check()])
    receipt = await verifier.verify(page)
    assert receipt["checks"][0]["actual"] == "10"
    assert receipt["status"] == "unconfirmed"
    assert not verifier.matched


async def test_ambiguous_identity_and_invalidation(live):
    page, _ = live
    html = '<article><h2>Invoice A</h2><input value="100"></article>'
    await page.route("http://outcome.test/", lambda route: route.fulfill(body=html, content_type="text/html"))
    await page.goto("http://outcome.test/")
    verifier = OutcomeVerifier([check()])
    assert (await verifier.verify(page))["status"] == "matched_after_reload"
    verifier.invalidate()
    assert not verifier.matched
    html *= 2
    assert (await verifier.verify(page))["checks"][0]["reason"] == "identity_not_unique"
    assert not verifier.matched


def test_contract_rejects_weak_types_and_empty_checks():
    with pytest.raises(ValueError):
        OutcomeVerifier([])
    with pytest.raises(ValueError):
        check(kind="checked", expected="false")
    with pytest.raises(ValueError):
        OutcomeVerifier([check(), check()])
    with pytest.raises(ValueError):
        check(kind="attribute", attribute="data-secret")


async def test_explicit_readback_and_origin_boundary(live):
    page, _ = live
    await page.route("http://outcome.test/**", lambda route: route.fulfill(
        body='<article><h2>Invoice A</h2><input value="100"></article>', content_type="text/html"))
    await page.goto("http://outcome.test/edit")
    verifier = OutcomeVerifier([check()], readback_url="http://outcome.test/saved")
    assert (await verifier.verify(page))["status"] == "matched_after_reload"
    assert page.url == "http://outcome.test/saved"
    blocked = OutcomeVerifier([check()], readback_url="http://elsewhere.test/")
    assert (await blocked.verify(page))["status"] == "unconfirmed"
    assert page.url == "http://outcome.test/saved"
