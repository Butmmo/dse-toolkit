"""People provider: People Data Labs brought to ready_byok on the same terms as Hunter.

An example adapter (provider_examples/people_data_labs.json) that the generic provider
machinery can load and call, a body_json template so a nested search body keeps its
types, and the catalog entry flipped from candidate to ready_byok. No real key and no
real call: the transport is a fake that records what would have been sent.
Run: python tests/test_people_provider.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dse import enrich_providers as ep
from dse import waterfall as wf

FAILED = []


def check(label, fn):
    try:
        fn()
        print("PASS ", label)
    except Exception as e:  # noqa: BLE001
        FAILED.append(label)
        print("FAIL ", label, "-", e)


EXAMPLE = Path(ep.EXAMPLES) / "people_data_labs.json"
PDL_PAYLOAD = {
    "status": 200, "total": 2,
    "data": [
        {"full_name": "Ada Bright", "first_name": "Ada", "last_name": "Bright", "job_title": "Owner",
         "job_company_name": "Bright Care Ltd", "job_company_website": "brightcare.co.uk",
         "linkedin_url": "https://www.linkedin.com/in/adabright", "work_email": "ada@brightcare.co.uk"},
        {"full_name": "Sam Other", "first_name": "Sam", "last_name": "Other", "job_title": "Manager",
         "job_company_name": "Elsewhere Ltd", "job_company_website": "elsewhere.example",
         "linkedin_url": "https://www.linkedin.com/in/samother", "work_email": None},
    ],
}


def load_cfg(tmp: Path):
    providers = tmp / "enrich-providers"
    providers.mkdir(exist_ok=True)
    (providers / "people_data_labs.json").write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    ep.PROVIDERS = providers
    os.environ["PDL_API_KEY"] = "test-key-not-real"
    return ep.load("people_data_labs")


def t_example_shape():
    cfg = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert cfg["name"] == "people_data_labs" and cfg["key_env"] == "PDL_API_KEY"
    assert cfg["request"]["url"] == "https://api.peopledatalabs.com/v5/person/search"
    assert cfg["request"]["auth"] == {"in": "header", "name": "X-Api-Key"}
    assert "person_identity" in cfg["response_fields"]
    assert cfg["cost_per_call"] is None, "per-record pricing stays unpriced, like Hunter"


def t_loads_like_hunter():
    with tempfile.TemporaryDirectory() as td:
        cfg = load_cfg(Path(td))
        assert cfg["_key"] == "test-key-not-real"
        try:
            ep.load("people_data_labs_missing")
            raise AssertionError("a missing provider must refuse")
        except ep.ProviderError:
            pass


def t_body_json_keeps_types():
    cfg = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    body = ep.request_body(cfg["request"], lambda s: s.replace("{domain}", "brightcare.co.uk"))
    assert body["size"] == 10 and isinstance(body["size"], int)
    assert body["titlecase"] is True
    assert body["query"]["bool"]["must"][0]["term"]["job_company_website"] == "brightcare.co.uk"
    flat = ep.request_body({"body": {"domain": "{domain}"}}, lambda s: s.replace("{domain}", "x.co.uk"))
    assert flat == {"domain": "x.co.uk"}, "the flat body map still works for the other providers"


def t_parse_people():
    cfg = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    people = ep.parse_field(cfg, PDL_PAYLOAD, "person_identity")
    assert len(people) == 2
    ada = people[0]["value"]
    assert ada["name"] == "Ada Bright" and ada["title"] == "Owner"
    assert ada["domain"] == "brightcare.co.uk" and ada["company"] == "Bright Care Ltd"
    assert people[0]["source_url"] == "https://www.linkedin.com/in/adabright"
    emails = ep.parse(cfg, PDL_PAYLOAD)
    assert [e["email"] for e in emails] == ["ada@brightcare.co.uk"], "a work email is used when the plan returns one"


def t_acceptance_anchors_to_the_lead():
    cfg = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    people = ep.parse_field(cfg, PDL_PAYLOAD, "person_identity")
    ok, _ = wf.accept_field_candidate("person_identity", people[0], "brightcare.co.uk", "Bright Care Ltd", "")
    assert ok, "the person at the lead's own domain is accepted"
    ok2, why2 = wf.accept_field_candidate("person_identity", people[1], "brightcare.co.uk", "Bright Care Ltd", "")
    assert not ok2 and why2 == "person_identity_not_anchored_to_lead"


def t_lookup_field_sends_the_search():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = load_cfg(tmp)
        ep.CACHE = tmp / "cache"
        ep._record_usage = lambda *a, **k: None
        sent = {}

        class Resp:
            status_code = 200

            def json(self):
                return PDL_PAYLOAD

        def fake_post(url, params=None, json=None, headers=None, timeout=None):
            sent.update(url=url, body=json, headers=headers)
            return Resp()

        ep.requests = SimpleNamespace(post=fake_post, get=None, RequestException=Exception)
        out = ep.lookup_field(cfg, "person_identity", {"domain": "brightcare.co.uk", "company": "Bright Care Ltd", "contact_name": ""}, ep.Budget(5))
        assert sent["url"].endswith("/v5/person/search")
        assert sent["headers"]["X-Api-Key"] == "test-key-not-real"
        assert sent["body"]["query"]["bool"]["must"][0]["term"]["job_company_website"] == "brightcare.co.uk"
        assert [c["value"]["name"] for c in out] == ["Ada Bright", "Sam Other"]


def t_catalog_says_ready():
    catalog = json.loads((Path(ep.EXAMPLES).parent / "enrichment_provider_catalog.json").read_text(encoding="utf-8"))
    entry = next(p for p in catalog["providers"] if p["id"] == "people_data_labs")
    assert entry["integration"] == "ready_byok"
    assert "person_identity" in entry["fields"]


check("the example adapter is shaped for the Person Search API", t_example_shape)
check("the example loads through the same door as Hunter, key from its env variable", t_loads_like_hunter)
check("body_json fills the domain and keeps numbers and nesting as real JSON types", t_body_json_keeps_types)
check("a recorded search answer parses into people, and a work email when present", t_parse_people)
check("the waterfall accepts only the person anchored to the lead's domain or company", t_acceptance_anchors_to_the_lead)
check("lookup_field sends the search with the member's key and returns the people", t_lookup_field_sends_the_search)
check("the provider catalog now marks People Data Labs ready_byok", t_catalog_says_ready)

print("\n%d FAILED" % len(FAILED) if FAILED else "\nALL PASS")
sys.exit(1 if FAILED else 0)
