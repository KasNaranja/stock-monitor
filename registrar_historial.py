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
import re
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
PAT_TRADEINN = re.compile(r"TRADEINN_(\d{8})_(\d{4})")


def consultar_tradeinn(host, user, pwd, dias=16):
    """Reconstruye el historial de subidas leyendo la carpeta 'log' de Tradeinn.

    Tradeinn procesa cada fichero y lo mueve a 'log', asi que la raiz suele estar
    vacia. El nombre de cada fichero lleva la fecha/hora de subida
    (TRADEINN_YYYYMMDD_HHMM), que es la fuente fiable del historial.
    """
    f = ftplib.FTP(host, timeout=40)
    f.login(user, pwd)
    try:
        nombres = f.nlst("log")
    except Exception:
        nombres = []
    f.quit()

    subidas = {}
    for n in nombres:
        base = n.split("/")[-1]
        m = PAT_TRADEINN.search(base)
        if not m:
            continue
        dt = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M").replace(
            tzinfo=datetime.timezone.utc)
        subidas.setdefault(dt, base)  # una entrada por fecha de subida
    if not subidas:
        return None

    ordenadas = sorted(subidas.items())
    ultima_dt, ultima_nombre = ordenadas[-1]
    corte = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=dias)
    eventos = [{"mtime": a_iso(dt), "fichero": base}
               for dt, base in ordenadas if dt >= corte]
    return {
        "actual": {"ultimo_fichero": ultima_nombre, "mtime": a_iso(ultima_dt)},
        "eventos": eventos,
    }


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
            if info:
                # La carpeta 'log' es la fuente completa: se reconstruye entera.
                data["procesos"]["subir_tradeinn"] = info
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
