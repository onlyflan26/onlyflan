# ONLYFLAN

Tienda con Flask, catálogo, carrito local y pedidos por WhatsApp. Los pedidos y los nombres de clientes no se guardan en el servidor. El visitante confirma el envío del mensaje en WhatsApp.

## Ejecutar en Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app init-db
.\.venv\Scripts\python.exe -m flask --app app create-admin
.\.venv\Scripts\python.exe app.py
```

Abrir http://127.0.0.1:5000. Panel: http://127.0.0.1:5000/panel.

El comando de creación pide usuario y contraseña (mínimo 10 caracteres) sin mostrar la contraseña. No existen cuentas ni contraseñas predeterminadas. El dueño crea y desactiva vendedores desde el panel. Los vendedores solo cambian disponibilidad; productos agotados se ocultan del catálogo y se retiran del carrito al actualizarlo.

## Configuración y servidor

- Local: SQLite en `instance/onlyflan.db`.
- Servidor: configurar `DATABASE_URL=postgresql+psycopg://...` y ejecutar `init-db` en esa base. Cambiar de base no migra datos automáticamente.
- Configurar `SECRET_KEY` aleatoria y estable; localmente se genera en `instance/secret.key`.
- Configurar `HTTPS_ONLY=1` detrás de HTTPS en producción. Usar proxy inverso con certificado TLS delante de Waitress, enlazado a loopback. El puerto local predeterminado es 5000, configurable con `PORT`.
- Persistir y respaldar la base de datos y `assets/uploads/`. No subir `instance/secret.key` ni credenciales al repositorio. Las imágenes originales aprobadas están en `assets/productos/`.
- El número de prueba es `59157002285`. El administrador puede reemplazarlo en el panel. El pago y la entrega se coordinan por WhatsApp.
- El límite de intentos de acceso reside en memoria por proceso; para varios procesos o instancias, usar un limitador compartido antes del despliegue.
- `init-db` carga los siete sabores a Bs 70 cuando la tabla de productos está vacía. Ejecutarlo para la instalación inicial, no como parte de cada arranque.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

La suite usa una base temporal y valida permisos, disponibilidad pública, carga/edición/eliminación de productos, desactivación de vendedores y protección CSRF.

Esta versión se prepara localmente para revisión; todavía no está desplegada en un servidor público.

## Más decorado

En el panel, editar un producto y activar Ofrecer decoración adicional. Indicar el recargo por unidad en Bs (puede ser cero) y guardar. Cada producto puede tener un importe distinto. Desactivar la casilla deja de ofrecer la variante; el carrito retira únicamente las unidades decoradas al actualizarse. El clásico y Más decorado se mantienen como líneas separadas y se identifican en WhatsApp. Los vendedores no pueden configurar precios.

Para actualizar una instalación existente sin cambiar sus datos: `.\.venv\Scripts\python.exe -m flask --app app upgrade-db`. Respaldar la base antes de actualizar en producción. Prueba del carrito y mensaje: `node test_cart.cjs`.

