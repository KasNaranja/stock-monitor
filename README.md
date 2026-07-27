# Monitor de stock · Toni Pons

Panel público que muestra **cuándo se actualizan** los ficheros de stock de Toni
Pons (`Stock Total.csv` y `Stock Marketplaces.csv`) en su Storage Box.

Solo contiene **fechas y tamaños** de los ficheros — nunca stock, precios ni
credenciales.

## Cómo funciona

- `registrar_historial.py` se conecta por SFTP cada 30 min (GitHub Actions) y
  apunta la fecha de última modificación de cada fichero en `historial.json`.
- `index.html` es el panel: lee ese historial y lo dibuja (línea de tiempo,
  frecuencia, última actualización). Se publica con **GitHub Pages**.

## Configuración (una vez)

1. Secret `SFTP_CONN` (Settings → Secrets → Actions) con formato
   `host|usuario|contraseña`.
2. Activar GitHub Pages (Settings → Pages → Deploy from a branch → `main` / root).

El panel se actualiza solo cada 30 min.
