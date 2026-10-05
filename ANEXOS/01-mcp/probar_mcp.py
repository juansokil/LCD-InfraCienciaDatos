#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prueba el servidor MCP de Airflow contra el stack del curso. SIN cliente MCP.

    python ANEXOS/01-mcp/probar_mcp.py

POR QUE NO HACE FALTA CLAUDE CODE NI CURSOR
Un servidor MCP por stdio habla JSON-RPC: mensajes JSON, uno por linea, por la
entrada y la salida estandar del proceso. O sea que se lo puede manejar desde un
script. Eso es exactamente lo que hace este archivo, y sirve para entender que
un "servidor MCP" no tiene nada de magico: es un proceso que recibe pedidos y
contesta.

LO QUE HACE, EN ORDEN
    1. initialize                -> arranca y negocia la version del protocolo
    2. notifications/initialized -> avisa que esta listo
    3. tools/list                -> que herramientas expone
    4. tools/call                -> llama dos de lectura y muestra la respuesta

REQUISITOS
    - El stack del curso levantado (docker compose up -d desde stack/).
    - `uv` instalado: https://docs.astral.sh/uv/  (trae el comando `uvx`).

SOLO LECTURA: se pasa AF_READ_ONLY=true, asi que el servidor bloquea todo lo
que escriba. No puede disparar, pausar, limpiar ni borrar nada.

OJO: `uvx` descarga el paquete de PyPI y lo ejecuta en tu maquina, con las
credenciales de tu Airflow. Es la forma normal de usar estos servidores, pero
conviene saberlo. La primera corrida puede tardar un minuto bajando todo.
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading

# ============================================================
# CONFIG — apunta al stack del curso
# ============================================================
SERVIDOR = ["uvx", "astro-airflow-mcp", "--transport", "stdio"]
ENTORNO = {
    "AIRFLOW_API_URL": "http://localhost:8080",
    "AIRFLOW_USERNAME": "admin",
    "AIRFLOW_PASSWORD": "admin",
    "AF_READ_ONLY": "true",          # <- el seguro: bloquea toda escritura
}
PROTOCOLO = "2025-06-18"
TIMEOUT_ARRANQUE = 180               # la 1ra vez uvx baja dependencias
TIMEOUT_NORMAL = 90
TIMEOUT_LARGO = 240              # las herramientas "consolidadas" encadenan varias llamadas


def _lector(pipe, cola):
    """Lee lineas del proceso en un hilo aparte: en Windows no hay select()."""
    for linea in iter(pipe.readline, ""):
        cola.put(linea)
    pipe.close()


class Servidor:
    """Un servidor MCP por stdio, manejado a mano con JSON-RPC."""

    def __init__(self, comando, entorno):
        env = {**os.environ, **entorno}
        self.proc = subprocess.Popen(
            comando, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", bufsize=1, env=env,
        )
        self.cola = queue.Queue()
        for pipe in (self.proc.stdout, self.proc.stderr):
            threading.Thread(target=_lector, args=(pipe, self.cola), daemon=True).start()
        self._id = 0

    def pedir(self, metodo, params=None, timeout=TIMEOUT_NORMAL):
        """Manda un request y espera LA respuesta con ese id."""
        self._id += 1
        mio = self._id
        msg = {"jsonrpc": "2.0", "id": mio, "method": metodo}
        if params is not None:
            msg["params"] = params
        self._escribir(msg)
        while True:
            linea = self._leer(timeout)
            try:
                r = json.loads(linea)
            except json.JSONDecodeError:
                continue             # log del servidor por stderr: se ignora
            if r.get("id") == mio:
                if "error" in r:
                    raise RuntimeError(f"{metodo}: {r['error']}")
                return r.get("result", {})

    def avisar(self, metodo, params=None):
        """Notificacion: no lleva id y no espera respuesta."""
        msg = {"jsonrpc": "2.0", "method": metodo}
        if params is not None:
            msg["params"] = params
        self._escribir(msg)

    def _escribir(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _leer(self, timeout):
        try:
            return self.cola.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(
                f"el servidor no contesto en {timeout}s. "
                "Esta levantado el stack? (docker compose up -d desde stack/)"
            )

    def cerrar(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def texto_de(resultado):
    """Saca el texto de un result de tools/call."""
    partes = [c.get("text", "") for c in resultado.get("content", [])
              if c.get("type") == "text"]
    return "\n".join(partes).strip()


def recortar(s, n=900):
    s = s.strip()
    return s if len(s) <= n else s[:n] + f"\n   ... (+{len(s) - n} caracteres)"


def main():
    print("=" * 70)
    print(" Prueba del MCP de Airflow contra el stack del curso")
    print("=" * 70)

    if not shutil.which("uvx"):
        sys.exit("ERROR: no encuentro `uvx`. Instala uv: https://docs.astral.sh/uv/")

    print(f"\nLevantando el servidor:  {' '.join(SERVIDOR)}")
    print(f"Apuntando a:             {ENTORNO['AIRFLOW_API_URL']}")
    print(f"Modo solo lectura:       {ENTORNO['AF_READ_ONLY']}")
    print("(la primera vez tarda: uvx baja el paquete y sus dependencias)\n")

    srv = Servidor(SERVIDOR, ENTORNO)
    try:
        # --- 1) handshake -------------------------------------------------
        r = srv.pedir("initialize", {
            "protocolVersion": PROTOCOLO,
            "capabilities": {},
            "clientInfo": {"name": "probar-mcp-unsam", "version": "1.0"},
        }, timeout=TIMEOUT_ARRANQUE)
        info = r.get("serverInfo", {})
        print("1. initialize")
        print(f"   servidor:  {info.get('name', '?')} v{info.get('version', '?')}")
        print(f"   protocolo: {r.get('protocolVersion', '?')}")
        srv.avisar("notifications/initialized")

        # --- 2) que sabe hacer --------------------------------------------
        herramientas = srv.pedir("tools/list").get("tools", [])
        print(f"\n2. tools/list -> {len(herramientas)} herramientas")
        for h in herramientas[:10]:
            desc = (h.get("description") or "").split("\n")[0][:58]
            print(f"   - {h['name']:<28} {desc}")
        if len(herramientas) > 10:
            print(f"   ... y {len(herramientas) - 10} mas")

        nombres = [h["name"] for h in herramientas]

        # --- 3) la mas liviana: confirma que LLEGA a la API de Airflow -----
        version = next((n for n in nombres if "version" in n.lower()), None)
        if version:
            print(f"\n3. tools/call {version}")
            print("   " + recortar(texto_de(srv.pedir(
                "tools/call", {"name": version, "arguments": {}})), 300
            ).replace("\n", "\n   "))

        # --- 4) los DAGs del curso ----------------------------------------
        listar = next((n for n in nombres
                       if "dag" in n.lower() and ("list" in n.lower() or "get_dags" in n.lower())), None)
        if listar:
            print(f"\n4. tools/call {listar}")
            crudo = texto_de(srv.pedir("tools/call", {"name": listar, "arguments": {}}))
            # La respuesta es el JSON entero de la API: 20 mil caracteres. Para
            # ver que funciona alcanza con los nombres.
            try:
                dags = json.loads(crudo).get("dags", [])
                print(f"   {len(dags)} DAGs en tu Airflow:")
                for d in dags:
                    estado = "pausado" if d.get("is_paused") else "activo "
                    print(f"     [{estado}] {d.get('dag_id')}")
            except (json.JSONDecodeError, AttributeError):
                print("   " + recortar(crudo).replace("\n", "\n   "))
        else:
            print("\n4. No encontre una herramienta para listar DAGs. Las disponibles:")
            print("   " + ", ".join(nombres))

        # --- 5) la "consolidada": hace varias llamadas y tarda bastante ----
        salud = next((n for n in nombres if "health" in n.lower()), None)
        if salud:
            print(f"\n5. tools/call {salud}   (encadena varias llamadas: puede tardar)")
            try:
                print("   " + recortar(texto_de(srv.pedir(
                    "tools/call", {"name": salud, "arguments": {}}, timeout=TIMEOUT_LARGO)), 600
                ).replace("\n", "\n   "))
            except (RuntimeError, TimeoutError) as e:
                print(f"   no contesto ({e})")
                print("   No invalida la prueba: los pasos 1 a 4 ya mostraron la conexion.")

        # --- 6) el seguro, probado ----------------------------------------
        # OJO: AF_READ_ONLY NO esconde las herramientas de escritura -- siguen
        # en la lista. Lo que hace es bloquearlas CUANDO SE LLAMAN. Se prueba
        # con ids que no existen, asi no hay forma de romper nada.
        if "delete_dag_run" in nombres:
            print("\n6. El seguro: llamo a delete_dag_run con ids inventados")
            r = srv.pedir("tools/call", {"name": "delete_dag_run", "arguments": {
                "dag_id": "__no_existe__", "dag_run_id": "__no_existe__"}})
            t = texto_de(r)
            if "read-only" in t.lower() or "readonly" in t.lower():
                print("   BLOQUEADA. El servidor contesto ReadOnlyError sin tocar Airflow.")
            else:
                print("   OJO: no la bloqueo. Revisa que AF_READ_ONLY este en true.")
                print("   " + recortar(t, 300).replace("\n", "\n   "))

        print("\n" + "=" * 70)
        print(" OK. El servidor arranco, se autentico contra Airflow 3 y leyo datos.")
        print(" Nada se modifico: la unica escritura que se intento fue rechazada.")
        print("=" * 70)

    except (RuntimeError, TimeoutError) as e:
        print(f"\nFALLO: {e}", file=sys.stderr)
        sobrante = []
        while not srv.cola.empty():
            sobrante.append(srv.cola.get_nowait())
        if sobrante:
            print("\nLo ultimo que dijo el servidor:", file=sys.stderr)
            for l in sobrante[-15:]:
                print("   " + l.rstrip(), file=sys.stderr)
        sys.exit(1)
    finally:
        srv.cerrar()


if __name__ == "__main__":
    main()
