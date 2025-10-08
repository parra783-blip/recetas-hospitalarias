
RecetaApp v3 FINAL (fpdf2, DB en red o local)
---------------------------------------------
- Unidad fija: HOSPITAL BASICO DE CAYAMBE
- Especialidad (Combo): MEDICINA INTERNA / GINECOLOGÍA / CIRUGÍA GENERAL / PEDIATRÍA / MEDICINA OCUPACIONAL
- Menú para definir el próximo número CE/EH
- PDF A4 con márgenes; cambia a 'Letter' en pdf_layout.py si necesitas

Instalación:
1) pip install -r requirements.txt
2) Edita NETWORK_DB_DIR en app.py (ruta de red o C:\RecetasApp para local)
3) python app.py


=== AUTENTICACIÓN Y ROLES (NUEVO) ===
- Al abrir la app, se muestra una pantalla de inicio de sesión.
- El usuario es una CONTRACCIÓN: primeras letras de los dos NOMBRES + dos APELLIDOS (sin tildes, minúsculas).
  Ej.: "Juan Carlos Pérez Gómez" -> **jcpg**.
- La contraseña es el número de CÉDULA de la hoja Excel "LISTADO NOMBRES.xlsx".
- El Excel debe contener columnas (cualquier nombre equivalente): NOMBRES, APELLIDOS, CEDULA, ESPECIALIDAD, ROL.
  ROL acepta "RESIDENTE" o "ESPECIALISTA".

Comportamiento por rol:
- RESIDENTE: Solo puede emitir **EM (Amarillo)** y **EH (Rojo)**. 
  El campo Servicio/Especialidad se fija en "MÉDICO RESIDENTE" y no se puede cambiar.
  El campo "Especialidad" queda deshabilitado.
- ESPECIALISTA: En **CE (Azul)**, el campo Servicio se fija automáticamente a su especialidad.

Otros:
- Se añadió "Fecha de Nacimiento (dd/mm/aaaa)". Al ingresar, la app calcula **Edad (años)** y **Meses** automáticamente.
- Botón **Imprimir Indicaciones**: genera un PDF aparte solo con el bloque de indicaciones.

