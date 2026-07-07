"""Test suite per il convertitore JSON → XML con validazione XSD."""

import io
import json
import sys
import os

# Aggiungi la directory padre al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


# ── XSD di test ────────────────────────────────────────────────────

VALID_XSD = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="root">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="name" type="xs:string"/>
        <xs:element name="age" type="xs:integer"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>"""

# XSD che richiede un elemento "email" che il JSON di test NON ha
MISMATCH_XSD = b"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="root">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="name" type="xs:string"/>
        <xs:element name="email" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>"""

INVALID_XSD = b"""<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="root">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="name" type="xs:unknownType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>"""


# ── Test: conversione JSON valido ──────────────────────────────────

def test_valid_json_conversion(client):
    """Un JSON valido deve produrre XML ben formato."""
    data = {
        "json_file": (io.BytesIO(b'{"name": "Mario", "age": 30}'), "test.json"),
    }
    resp = client.post("/api/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200

    body = resp.get_json()
    assert body["success"] is True
    assert body["xml"].startswith('<?xml version="1.0"')
    assert "<name>Mario</name>" in body["xml"]
    assert "<age>30</age>" in body["xml"]
    assert body["validation"] is None  # nessun XSD caricato


def test_valid_json_with_array_root(client):
    """Un JSON con array alla radice deve essere gestito."""
    data = {
        "json_file": (io.BytesIO(b'["a", "b", "c"]'), "array.json"),
    }
    resp = client.post("/api/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200

    body = resp.get_json()
    assert body["success"] is True
    assert "<item>a</item>" in body["xml"]
    assert "<item>b</item>" in body["xml"]
    assert "<item>c</item>" in body["xml"]


def test_nested_json(client):
    """Un JSON annidato deve essere convertito correttamente."""
    data = {
        "json_file": (io.BytesIO(b'{"person": {"name": "Luigi", "city": "Roma"}}'), "nested.json"),
    }
    resp = client.post("/api/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200

    body = resp.get_json()
    assert body["success"] is True
    assert "<person>" in body["xml"]
    assert "<name>Luigi</name>" in body["xml"]
    assert "<city>Roma</city>" in body["xml"]


# ── Test: validazione XSD ──────────────────────────────────────────

def test_xsd_validation_pass(client):
    """JSON + XSD compatibile → validazione superata."""
    data = {
        "json_file": (io.BytesIO(b'{"name": "Mario", "age": 30}'), "test.json"),
        "xsd_file": (io.BytesIO(VALID_XSD), "schema.xsd"),
    }
    resp = client.post("/api/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200

    body = resp.get_json()
    assert body["success"] is True
    assert body["validation"] is not None
    assert body["validation"]["passed"] is True
    assert body["validation"]["errors"] == []


def test_xsd_validation_fail(client):
    """JSON + XSD incompatibile → validazione fallita."""
    data = {
        "json_file": (io.BytesIO(b'{"name": "Mario", "age": 30}'), "test.json"),
        "xsd_file": (io.BytesIO(MISMATCH_XSD), "schema.xsd"),
    }
    resp = client.post("/api/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200

    body = resp.get_json()
    assert body["success"] is True
    assert body["validation"] is not None
    assert body["validation"]["passed"] is False
    assert len(body["validation"]["errors"]) > 0


# ── Test: errori ───────────────────────────────────────────────────

def test_malformed_json(client):
    """JSON malformato → errore chiaro."""
    data = {
        "json_file": (io.BytesIO(b'{name: broken,}'), "bad.json"),
    }
    resp = client.post("/api/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400

    body = resp.get_json()
    assert body["success"] is False
    assert "JSON" in body["error"].upper() or "json" in body["error"].lower()


def test_empty_json_file(client):
    """File JSON vuoto → errore."""
    data = {
        "json_file": (io.BytesIO(b''), "empty.json"),
    }
    resp = client.post("/api/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400

    body = resp.get_json()
    assert body["success"] is False


def test_no_file_uploaded(client):
    """Nessun file → errore."""
    resp = client.post("/api/convert", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400

    body = resp.get_json()
    assert body["success"] is False


def test_no_filename(client):
    """File senza nome → errore."""
    data = {
        "json_file": (io.BytesIO(b'{}'), ""),
    }
    resp = client.post("/api/convert", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400

    body = resp.get_json()
    assert body["success"] is False


# ── Test: pagina principale ────────────────────────────────────────

def test_index_page(client):
    """La pagina principale deve essere servita."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Convertitore JSON" in resp.data


def test_robots_txt(client):
    """robots.txt deve essere accessibile."""
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert b"User-agent" in resp.data


def test_sitemap_xml(client):
    """sitemap.xml deve essere accessibile."""
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert b"urlset" in resp.data
