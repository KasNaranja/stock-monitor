"""
Registra el estado del pipeline de stock en 'historial.json' para el panel.

Secciones que alimenta:
  1) ficheros    -> ACTUALIZACION FTP TONI PONS (SFTP origen). Requiere SFTP_CONN.
  3) subir_tradeinn -> SUBIR STOCK A TRADEINN (FTP Tradeinn). Requiere TRADEINN_CONN.
  (2) copiar_github -> lo reporta el propio robot privado; aqui no se toca.

Los datos de conexion vienen de Secrets (formato host|usuario|contrasena); nada
sensible queda en el codigo. Se ejecuta cada 30 min en GitHub Actions.
"""

import datetime
import ftplib
import json
import os
import sys

import paramiko

SFTP_PORT = 23
FICHEROS = ["Stock Total.csv", "Stock Marketplaces.csv"]
HIST = "historial.json"


def ahora_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def a_iso(dt):
    return dt.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat()


def parse_conn(nombre, obligatorio=True):
    conn = os.environ.get(nombre)
    if not conn or conn.count("|") != 2:
        if obligatorio:
            print(f"ERROR: falta el Secret {nombre} (host|usuario|contrasena)",
                  file=sys.stderr)
            sys.exit(1)
        return None
    host, user, pwd = conn.split("|")
    return host.strip(), user.strip(), pwd


# ---------------------------------------------------------------------------
# Seccion 1: origen (SFTP Toni Pons)
# ---------------------------------------------------------------------------
def consultar_origen(host, user, pwd):
    t = paramiko.Transport((host, SFTP_PORT))
    t.connect(username=user, password=pwd)
    s = paramiko.SFTPClient.from_transport(t)
    res = {}
    for f in FICHEROS:
        a = s.stat(f)
        mt = datetime.datetime.fromtimestamp(a.st_mtime, datetime.timezone.utc)
        res[f] = {"mtime": a_iso(mt), "size": int(a.st_size)}
    t.close()
    return res


# ---------------------------------------------------------------------------
# Seccion 3: destino (FTP Tradeinn)
# ---------------------------------------------------------------------------
def consultar_tradeinn(host, user, pwd):
    """Devuelve el fichero mas reciente subido al FTP de Tradeinn (ignora 'log')."""
    f = ftplib.FTP(host, timeout=40)
    f.login(user, pwd)
    ficheros = []
    try:
        for nombre, facts in f.mlsd():
            if facts.get("type") != "file":
                continue
            modify = facts.get("modify")  # YYYYMMDDHHMMSS (UTC)
            if not modify:
                continue
            dt = datetime.datetime.strptime(modify, "%Y%m%d%H%M%S").replace(
                tzinfo=datetime.timezone.utc)
            ficheros.append((nombre, dt, int(facts.get("size", 0))))
    except ftplib.error_perm:
        # Fallback si el servidor no soporta MLSD
        nombres = f.nlst()
        for nombre in nombres:
            if nombre in (".", "..", "log"):
                continue
            try:
                r = f.sendcmd("MDTM " + nombre)  # 213 YYYYMMDDHHMMSS
                dt = datetime.datetime.strptime(r.split()[1], "%Y%m%d%H%M%S").replace(
                    tzinfo=datetime.timezone.utc)
                size = f.size(nombre) or 0
                ficheros.append((nombre, dt, size))
            except Exception:
                continue
    f.quit()
    if not ficheros:
        return None
    ficheros.sort(key=lambda x: x[1])
    nombre, dt, size = ficheros[-1]
    return {"ultimo_fichero": nombre, "mtime": a_iso(dt), "size": size,
            "num_ficheros": len(ficheros)}


def main():
    data = {"ficheros": {}, "procesos": {}}
    if os.path.exists(HIST):
        with open(HIST, encoding="utf-8") as fh:
            data = json.load(fh)
    data.setdefault("ficheros", {})
    data.setdefault("procesos", {})
    data["ultima_comprobacion"] = ahora_iso()

    # --- Seccion 1 ---
    host, user, pwd = parse_conn("SFTP_CONN", obligatorio=True)
    for fichero, info in consultar_origen(host, user, pwd).items():
        fd = data["ficheros"].setdefault(fichero, {"eventos": []})
        ev = fd.setdefault("eventos", [])
        fd["actual"] = info
        if not ev or ev[-1]["mtime"] != info["mtime"]:
            ev.append({"mtime": info["mtime"], "size": info["size"],
                       "detectado": data["ultima_comprobacion"]})

    # --- Seccion 3 (opcional) ---
    tconn = parse_conn("TRADEINN_CONN", obligatorio=False)
    if tconn:
        try:
            info = consultar_tradeinn(*tconn)
            proc = data["procesos"].setdefault("subir_tradeinn", {"eventos": []})
            ev = proc.setdefault("eventos", [])
            if info:
                proc["actual"] = info
                if not ev or ev[-1].get("mtime") != info["mtime"]:
                    ev.append({"mtime": info["mtime"], "fichero": info["ultimo_fichero"],
                               "size": info["size"], "detectado": data["ultima_comprobacion"]})
        except Exception as e:
            print("Aviso: no se pudo leer el FTP de Tradeinn:", e, file=sys.stderr)

    with open(HIST, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    print("Historial actualizado:", data["ultima_comprobacion"])
    for fichero, fd in data["ficheros"].items():
        print(f"  [origen] {fichero}: {len(fd['eventos'])} ev | {fd['actual']['mtime']}")
    st = data["procesos"].get("subir_tradeinn", {}).get("actual")
    if st:
        print(f"  [tradeinn] ultimo: {st['ultimo_fichero']} | {st['mtime']}")


if __name__ == "__main__":
    main()
