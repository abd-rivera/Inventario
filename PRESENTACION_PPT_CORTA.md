# Plus Control - PPT Corta (6 diapositivas)

## Diapositiva 1: Portada
**Titulo:** Plus Control  
**Subtitulo:** Sistema de Inventario y Ventas para pequenos negocios  
**Autor:** [Tu nombre]  
**Fecha:** Marzo 2026

**Que decir (20-30s):**
- Plus Control es una aplicacion web para controlar inventario, registrar ventas y ver reportes semanales en un solo lugar.
- Fue construida como MVP funcional, lista para desplegar en la nube.

---

## Diapositiva 2: Problema y Objetivo
**Problema:**
- Muchos negocios llevan inventario en papel o Excel.
- Esto genera errores en stock, ventas no registradas y poca visibilidad del negocio.

**Objetivo de Plus Control:**
- Centralizar inventario y ventas.
- Reducir errores manuales.
- Dar visibilidad con metricas y reportes rapidos.

**Que decir (30-40s):**
- El foco no es solo guardar productos, sino conectar inventario con ventas para que el dueno tome decisiones rapidas.

---

## Diapositiva 3: Solucion y Funcionalidades
**Funciones principales:**
- Autenticacion con registro, login y verificacion por correo (OTP).
- CRUD de inventario: crear, editar, eliminar y buscar productos.
- Control de stock bajo con alertas.
- Registro de ventas con metodos de pago (Efectivo/Yappy).
- Dashboard con KPIs y graficas (ventas semanales, top productos).
- Reporte semanal por metodo de pago.
- Backup de base de datos y factura PDF por venta.

**Que decir (40-50s):**
- El sistema esta pensado para operar dia a dia: cargar productos, vender, ver resumen y respaldar informacion.

---

## Diapositiva 4: Arquitectura Tecnica (simple)
**Stack:**
- Frontend: HTML, CSS, JavaScript (vanilla) + Chart.js.
- Backend: Flask (Python).
- Base de datos: SQLite (`back/data/inventory.db`).
- Deploy: Render con Gunicorn y disco persistente.

**Flujo:**
- Usuario -> Frontend -> API Flask (`/api/...`) -> SQLite

**Endpoints clave:**
- Auth: `/api/auth/register`, `/api/auth/verify-email`, `/api/auth/login`
- Inventario: `/api/items` (GET/POST/PUT/DELETE)
- Ventas: `/api/sales` (GET/POST), `/api/reports/weekly`, `/api/backup`

**Que decir (40-50s):**
- Se eligio arquitectura simple para velocidad de implementacion y mantenimiento.
- El backend tambien sirve el frontend, simplificando despliegue inicial.

---

## Diapositiva 5: Demo Rapida (flujo sugerido)
**Demo en 4 pasos (2 min):**
1. Login/registro con verificacion de correo.
2. Crear o editar un producto en inventario.
3. Registrar una venta (Efectivo o Yappy).
4. Mostrar impacto: baja stock, sube total vendido y aparece en reporte semanal.

**Mensaje clave:**
- "Una accion de venta actualiza inventario y metricas automaticamente."

---

## Diapositiva 6: Estado Actual y Proximos Pasos
**Estado actual:**
- MVP funcional completado y listo para deploy.
- Configuracion para Render definida (`render.yaml`).

**Proximos pasos:**
- Despliegue productivo y pruebas con usuarios reales.
- Integrar pagos online (Stripe).
- Evolucion a modelo SaaS multi-tenant.
- Mejoras de analitica y reportes.

**Cierre (20-30s):**
- Plus Control resuelve una necesidad real con una base tecnica solida y escalable por etapas.

---

## Diseno recomendado (visual rapido)
- Usa una plantilla limpia de 16:9.
- Colores sugeridos: azul oscuro + acento verde (profesional y financiero).
- 1 idea por diapositiva, poco texto, mas capturas del sistema.
- Inserta 2-3 screenshots: login, dashboard, ventas/reporte.

## Duracion total estimada
- 4 a 6 minutos.
