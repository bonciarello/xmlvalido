"""Convertitore JSON → XML — backend Flask con validazione XSD opzionale."""

import os
import json
import io
from flask import Flask, request, jsonify, render_template, send_from_directory
import xmltodict
from lxml import etree


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload


def _json_to_xml(data) -> str:
    """Converte un dict/list Python in stringa XML ben formata."""
    # xmltodict.unparse richiede un dict con una singola chiave radice
    if isinstance(data, list):
        wrapped = {"root": {"item": data}}
    elif isinstance(data, dict):
        wrapped = {"root": data}
    else:
        # scalare solitario (es. "hello" o 42)
        wrapped = {"root": str(data)}

    body = xmltodict.unparse(wrapped, pretty=True, full_document=False)
    # xmltodict produce <root>…</root> senza dichiarazione XML
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


def _validate_xml(xml_str: str, xsd_bytes: bytes) -> dict:
    """Valida una stringa XML contro uno schema XSD (bytes).
    Restituisce {'passed': bool, 'errors': [str]}."""
    try:
        xsd_doc = etree.fromstring(xsd_bytes)
        schema = etree.XMLSchema(xsd_doc)
        xml_doc = etree.fromstring(xml_str.encode("utf-8"))
        schema.assertValid(xml_doc)
        return {"passed": True, "errors": []}
    except etree.XMLSchemaError as e:
        return {"passed": False, "errors": [f"XSD non valido: {e}"]}
    except etree.DocumentInvalid as e:
        return {"passed": False, "errors": [f"XML non conforme allo schema: {e}"]}
    except etree.XMLSyntaxError as e:
        return {"passed": False, "errors": [f"Errore di sintassi XML: {e}"]}
    except Exception as e:
        return {"passed": False, "errors": [f"Errore di validazione: {e}"]}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/robots.txt")
def robots():
    return send_from_directory("static", "robots.txt")


@app.route("/sitemap.xml")
def sitemap():
    return send_from_directory("static", "sitemap.xml")


@app.route("/api/convert", methods=["POST"])
def convert():
    # --- validazione input ---------------------------------------------------
    if "json_file" not in request.files:
        return jsonify({"success": False, "error": "Nessun file JSON caricato."}), 400

    json_file = request.files["json_file"]
    if not json_file.filename:
        return jsonify({"success": False, "error": "Nessun file selezionato."}), 400

    # --- parsing JSON --------------------------------------------------------
    try:
        raw = json_file.read()
        if len(raw) == 0:
            return jsonify({"success": False, "error": "Il file JSON è vuoto."}), 400
        text = raw.decode("utf-8")
        data = json.loads(text)
    except UnicodeDecodeError:
        return jsonify({"success": False, "error": "Il file non è codificato in UTF-8."}), 400
    except json.JSONDecodeError as e:
        return jsonify({"success": False, "error": f"JSON malformato: {e}"}), 400

    # --- conversione JSON → XML ----------------------------------------------
    try:
        xml_str = _json_to_xml(data)
    except Exception as e:
        return jsonify({"success": False, "error": f"Errore durante la conversione: {e}"}), 500

    # --- validazione XSD opzionale -------------------------------------------
    validation_result = None
    xsd_file = request.files.get("xsd_file")
    if xsd_file and xsd_file.filename:
        try:
            xsd_bytes = xsd_file.read()
            if len(xsd_bytes) == 0:
                return jsonify({"success": False, "error": "Il file XSD è vuoto."}), 400
            validation_result = _validate_xml(xml_str, xsd_bytes)
        except Exception as e:
            return jsonify({"success": False, "error": f"Errore nella lettura dell'XSD: {e}"}), 400

    return jsonify({
        "success": True,
        "xml": xml_str,
        "validation": validation_result,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4600))
    app.run(host="0.0.0.0", port=port, debug=False)
