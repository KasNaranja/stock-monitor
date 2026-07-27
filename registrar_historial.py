"""
Registra la fecha de ultima modificacion de los 2 ficheros de stock del
Storage Box de Toni Pons en 'historial.json', para el panel de monitorizacion.

Se ejecuta cada 30 min en GitHub Actions (repo PUBLICO). NO contiene datos de
stock ni credenciales: los datos de conexion vienen del Secret 'SFTP_CONN'
(formato: host|usuario|contrasena), asi que nada sensible queda en el codigo.
"""

import datetime
import json
import os
import sys

import paramiko

PORT = 23
FICHEROS = ["Stock Total.csv", "Stock Marketplaces.csv"]
HIST = "historial.json"


def ahora_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def mtime_iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).replace(
        microsecond=0).isoformat()


def leer_conexion():
    conn = os.environ.get("SFTP_CONN")
    if not conn or conn.count("|") != 2:
        print("ERROR: falta el Secret SFTP_CONN (formato host|usuario|contrasena)",
              file=sys.stderr)
        sys.exit(1)
    host, user, pwd = conn.split("|")
    return host.strip(), user.strip(), pwd


def consultar(host, user, pwd):
    t = paramiko.Transport((host, PORT))
    t.connect(username=user, password=pwd)
    s = paramiko.SFTPClient.from_transport(t)
    res = {}
    for f in FICHEROS:
        a = s.stat(f)
        res[f] = {"mtime": mtime_iso(a.st_mtime), "size": int(a.st_size)}
    t.close()
    return res


def main():
    host, user, pwd = leer_conexion()

    data = {"ficheros": {}}
    if os.path.exists(HIST):
        with open(HIST, encoding="utf-8") as f:
            data = json.load(f)
    data.setdefault("ficheros", {})
    data["ultima_comprobacion"] = ahora_iso()

    actual = consultar(host, user, pwd)
    for fichero, info in actual.items():
        fd = data["ficheros"].setdefault(fichero, {"eventos": []})
        eventos = fd.setdefault("eventos", [])
        fd["actual"] = info
        # Nuevo evento solo si la fecha de modificacion ha cambiado.
        if not eventos or eventos[-1]["mtime"] != info["mtime"]:
            eventos.append({"mtime": info["mtime"], "size": info["size"],
                            "detectado": data["ultima_comprobacion"]})

    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("Historial actualizado:", data["ultima_comprobacion"])
    for fichero, fd in data["ficheros"].items():
        print(f"  {fichero}: {len(fd['eventos'])} eventos | ultimo {fd['actual']['mtime']}")


if __name__ == "__main__":
    main()
