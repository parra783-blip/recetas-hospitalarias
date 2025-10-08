"""
Enhanced Prescription System with Integrated Security and Audit Features
Complies with Ley Orgánica de Salud requirements for traceability, 
professional validation, and data protection.
FIXED VERSION - CIE-10 and Medications lists working
"""

import os
import sqlite3
import uuid
import json
import csv
import re
import platform
import subprocess
import hashlib
import logging
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import pandas as pd

# Import the FIXED PDF layout
from pdf_layout_fixed import build_pdf

# Ruta del catálogo CIE-10 (CSV con columnas: code,desc)
CIE10_CSV = os.path.join(os.path.dirname(__file__), "cie10_es.csv")
# Ruta del catálogo de medicamentos
MEDICAMENTOS_CSV = os.path.join(os.path.dirname(__file__), "stock_medicamentos_dispositivos_HBC_2025-09-24.csv")

APP_TITLE = "Receta Electrónica Hospital Básico Cayambe by Dr.P."

# Cross-platform database directory
if platform.system() == "Windows":
    NETWORK_DB_DIR = r"C:\RecetasApp"
else:
    NETWORK_DB_DIR = os.path.expanduser("~/RecetasApp")

DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "output")

# Configure logging for audit trail
def setup_logging():
    """Configura el sistema de logging para auditoría"""
    log_dir = os.path.join(NETWORK_DB_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f"recetas_audit_{datetime.now().strftime('%Y%m')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    return logging.getLogger(__name__)

# Initialize logger
logger = setup_logging()

# Professional services mapping for validation
SERVICIOS_AUTORIZADOS = {
    "MEDICINA INTERNA": ["MEDICO GENERAL", "MEDICO INTERNISTA", "MEDICO ESPECIALISTA"],
    "GINECOLOGÍA": ["MEDICO GINECOLOGO", "MEDICO OBSTETRA", "MEDICO ESPECIALISTA"],
    "CIRUGÍA GENERAL": ["MEDICO CIRUJANO", "MEDICO ESPECIALISTA"],
    "PEDIATRÍA": ["MEDICO PEDIATRA", "MEDICO ESPECIALISTA"],
    "MEDICINA OCUPACIONAL": ["MEDICO OCUPACIONAL", "MEDICO GENERAL"],
    "EMERGENCIA": ["MEDICO GENERAL", "MEDICO ESPECIALISTA", "MEDICO EMERGENCIOLOGO"],
    "HOSPITALIZACIÓN": ["MEDICO GENERAL", "MEDICO ESPECIALISTA", "MEDICO INTERNISTA"],
}

def get_local_ip():
    """Obtiene la dirección IP local"""
    try:
        import socket
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except:
        return "127.0.0.1"

def calculate_hash(data):
    """Calcula hash SHA-256 para verificación de integridad"""
    try:
        data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(data_str.encode('utf-8')).hexdigest()
    except:
        return ""

def validate_professional_service(servicio, prescriptor_especialidad):
    # Validación desactivada: usamos especialidad del usuario y no hay servicio
    return True

def create_backup():
    """Crea respaldo de la base de datos"""
    try:
        backup_dir = os.path.join(NETWORK_DB_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"recetas_backup_{timestamp}.db")
        
        # Copiar base de datos
        import shutil
        shutil.copy2(db_path(), backup_file)
        
        logger.info(f"Respaldo creado: {backup_file}")
        return True
        
    except Exception as e:
        logger.error(f"Error creando respaldo: {e}")
        return False

def db_path():
    """Obtiene la ruta de la base de datos"""
    folder = NETWORK_DB_DIR
    try:
        os.makedirs(folder, exist_ok=True)
    except PermissionError:
        # Fallback to local directory if network path is not accessible
        folder = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "recetas.db")

def ensure_db():
    """Crea la base de datos y tablas si no existen - ENHANCED VERSION"""
    try:
        path = db_path()
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        
        # Crear tabla de secuencias
        cur.execute("""
            CREATE TABLE IF NOT EXISTS secuencias (
                tipo TEXT PRIMARY KEY, 
                ultimo INTEGER NOT NULL
            )
        """)
        
        # Crear tabla de recetas ENHANCED con campos de auditoría
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recetas (
                id TEXT PRIMARY KEY,
                numero TEXT NOT NULL UNIQUE,
                tipo TEXT NOT NULL,
                fecha TEXT,
                unidad TEXT, 
                servicio TEXT, 
                prescriptor TEXT,
                prescriptor_especialidad TEXT,
                paciente TEXT, 
                ci TEXT, 
                hc TEXT,
                edad TEXT, 
                meses TEXT, 
                sexo TEXT,
                talla TEXT, 
                peso TEXT,
                cie TEXT, 
                cie_desc TEXT,
                indicaciones TEXT,
                actividad_fisica TEXT,
                estado_enfermedad TEXT,
                alergias TEXT,
                alergias_especificar TEXT,
                payload TEXT,
                pdf_path TEXT,
                created_at TEXT,
                created_by TEXT,
                ip_address TEXT,
                hash_verificacion TEXT,
                estado TEXT DEFAULT 'ACTIVA',
                modificaciones TEXT
            )
        """)

        # Crear tabla de auditoría para trazabilidad completa
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auditoria (
                id TEXT PRIMARY KEY,
                receta_numero TEXT,
                accion TEXT,
                usuario TEXT,
                fecha_hora TEXT,
                ip_address TEXT,
                detalles TEXT,
                hash_anterior TEXT,
                hash_nuevo TEXT
            )
        """)

        # Crear tabla de accesos para bitácora de seguridad
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bitacora_accesos (
                id TEXT PRIMARY KEY,
                usuario TEXT,
                accion TEXT,
                fecha_hora TEXT,
                ip_address TEXT,
                detalles TEXT,
                resultado TEXT
            )
        """)

        # Crear tabla de respaldos
        cur.execute("""
            CREATE TABLE IF NOT EXISTS respaldos (
                id TEXT PRIMARY KEY,
                fecha_respaldo TEXT,
                tipo_respaldo TEXT,
                archivo_respaldo TEXT,
                estado TEXT,
                registros_respaldados INTEGER
            )
        """)

        # --- MIGRACIÓN DE ESQUEMA: agregar columnas nuevas si faltan ---
        try:
            cur.execute("PRAGMA table_info(recetas)")
            existing_cols = {row[1] for row in cur.fetchall()}
            needed = {
                "actividad_fisica": "TEXT",
                "estado_enfermedad": "TEXT",
                "alergias": "TEXT",
                "alergias_especificar": "TEXT",
                "prescriptor_especialidad": "TEXT",
                "created_at": "TEXT",
                "created_by": "TEXT", 
                "ip_address": "TEXT",
                "hash_verificacion": "TEXT",
                "estado": "TEXT DEFAULT 'ACTIVA'",
                "modificaciones": "TEXT"
            }
            for col, coltype in needed.items():
                if col not in existing_cols:
                    cur.execute(f"ALTER TABLE recetas ADD COLUMN {col} {coltype}")
        except Exception as e:
            logger.warning(f"Migración de esquema: {e}")

        # Inicializar secuencias
        for tipo in ("CE", "EH", "EM"):
            cur.execute(
                "INSERT OR IGNORE INTO secuencias(tipo, ultimo) VALUES(?,?)", 
                (tipo, -1)
            )

        conn.commit()
        conn.close()
        
        logger.info("Base de datos inicializada correctamente")
        return True
        
    except Exception as e:
        logger.error(f"Error al crear la base de datos: {str(e)}")
        messagebox.showerror("Error de Base de Datos", f"Error al crear la base de datos: {str(e)}")
        return False

def log_access(usuario, accion, detalles="", resultado="EXITOSO"):
    """Registra accesos en la bitácora de seguridad"""
    try:
        conn = sqlite3.connect(db_path())
        cur = conn.cursor()
        
        access_id = str(uuid.uuid4())
        ip_address = get_local_ip()
        fecha_hora = datetime.now().isoformat()
        
        cur.execute("""
            INSERT INTO bitacora_accesos 
            (id, usuario, accion, fecha_hora, ip_address, detalles, resultado)
            VALUES (?,?,?,?,?,?,?)
        """, (access_id, usuario, accion, fecha_hora, ip_address, detalles, resultado))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Acceso registrado: {usuario} - {accion} - {resultado}")
        
    except Exception as e:
        logger.error(f"Error registrando acceso: {e}")

def log_audit(receta_numero, accion, usuario, detalles="", hash_anterior="", hash_nuevo=""):
    """Registra eventos de auditoría para trazabilidad"""
    try:
        conn = sqlite3.connect(db_path())
        cur = conn.cursor()
        
        audit_id = str(uuid.uuid4())
        ip_address = get_local_ip()
        fecha_hora = datetime.now().isoformat()
        
        cur.execute("""
            INSERT INTO auditoria 
            (id, receta_numero, accion, usuario, fecha_hora, ip_address, detalles, hash_anterior, hash_nuevo)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (audit_id, receta_numero, accion, usuario, fecha_hora, ip_address, detalles, hash_anterior, hash_nuevo))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Auditoría registrada: {receta_numero} - {accion} - {usuario}")
        
    except Exception as e:
        logger.error(f"Error registrando auditoría: {e}")

def next_number(tipo):
    """Genera el siguiente número correlativo"""
    try:
        conn = sqlite3.connect(db_path())
        cur = conn.cursor()
        cur.execute("SELECT ultimo FROM secuencias WHERE tipo= ?", (tipo,))
        result = cur.fetchone()
        
        if not result:
            raise ValueError(f"Tipo de receta '{tipo}' no encontrado")
            
        ultimo = result[0] + 1
        cur.execute("UPDATE secuencias SET ultimo=? WHERE tipo=?", (ultimo, tipo))
        conn.commit()
        conn.close()
        
        return f"{tipo}-{datetime.now().year}-{ultimo:06d}"
        
    except Exception as e:
        logger.error(f"Error generando número: {e}")
        messagebox.showerror("Error", f"Error al generar número: {str(e)}")
        return None

def validate_ci(ci):
    """Valida el identificador del paciente (CI)"""
    if not ci:
        return False
    ci = ci.strip().replace(" ", "")
    if len(ci) < 10:
        return False
    return ci.isalnum()

def validate_numeric(value, field_name, min_val=0, max_val=None):
    """Valida que un valor sea numérico y esté en el rango especificado"""
    if not value or not str(value).strip():
        return True  # Campos opcionales
    
    try:
        num_val = float(value)
        if num_val < min_val:
            messagebox.showerror("Validación", f"{field_name} debe ser mayor o igual a {min_val}")
            return False
        if max_val is not None and num_val > max_val:
            messagebox.showerror("Validación", f"{field_name} debe ser menor o igual a {max_val}")
            return False
        return True
    except ValueError:
        messagebox.showerror("Validación", f"{field_name} debe ser un número válido")
        return False

def open_file_cross_platform(filepath):
    """Abre un archivo de manera multiplataforma"""
    try:
        if platform.system() == 'Darwin':       # macOS
            subprocess.call(('open', filepath))
        elif platform.system() == 'Windows':    # Windows
            os.startfile(filepath)
        else:                                   # linux variants
            subprocess.call(('xdg-open', filepath))
    except Exception as e:
        messagebox.showinfo("Archivo", f"No se pudo abrir automáticamente.\nRuta: {filepath}")


# === Gestión de usuarios desde Excel ===
def normalize_text(s: str) -> str:
    import unicodedata, re
    s = str(s or "").strip().lower()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9 ]+', '', s)
    return s

def contraction_username(nombres: str, apellidos: str) -> str:
    # Toma los dos primeros nombres y dos apellidos (si existen) y forma usuario con la primera letra de cada parte
    parts = (normalize_text(nombres).split()[:2] + normalize_text(apellidos).split()[:2])
    initials = ''.join([p[0] for p in parts if p])
    return initials or 'usuario'

def load_user_directory(excel_path: str):
    """
    Lee LISTADO NOMBRES.xlsx y devuelve un diccionario por usuario:
    {
        'username': {
            'password': <cedula>,
            'nombres': 'Juan Carlos',
            'apellidos': 'Perez Gomez',
            'nombre_completo': 'Juan Carlos Perez Gomez',
            'especialidad': 'CIRUGÍA GENERAL' / 'PEDIATRÍA' / etc,
            'rol': 'RESIDENTE' o 'ESPECIALISTA'
        }, ...
    }
    Columnas toleradas (cualquier combinación): 
    ['NOMBRES','APELLIDOS','CEDULA','ESPECIALIDAD','ROL','TIPO','CARGO']
    """
    import pandas as pd
    xls = pd.read_excel(excel_path)
    cols = {c.strip().lower(): c for c in xls.columns}
    def pick(*keys):
        for k in keys:
            if k in cols: return cols[k]
        return None
    col_nombres = pick('nombres','nombre','primer nombre','nombres y apellidos')
    col_apellidos = pick('apellidos','apellido')
    col_cedula = pick('cedula','cédula','dni','id','identificacion','identificación','numero de cedula','número de cédula','numero de cédula','num de cedula','nro de cedula','numero cedula')
    if not col_cedula:
        for k_norm, k_orig in cols.items():
            if 'cedul' in k_norm or k_norm.strip() == 'ci':
                col_cedula = k_orig
                break
    col_especialidad = pick('especialidad','servicio','area','área')
    col_rol = pick('rol','tipo','cargo','categoria')

    directory = {}
    for _, row in xls.iterrows():
        nombres = str(row.get(col_nombres, '') if col_nombres else '').strip()
        apellidos = str(row.get(col_apellidos, '') if col_apellidos else '').strip()
        cedula = str(row.get(col_cedula, '') if col_cedula else '').strip()
        especialidad = str(row.get(col_especialidad, '') if col_especialidad else '').strip().upper()
        rol = str(row.get(col_rol, '') if col_rol else '').strip().upper()
        if not cedula or not (nombres or apellidos):
            continue
        username = contraction_username(nombres, apellidos)
        directory[username] = {
            'password': cedula,
            'nombres': nombres,
            'apellidos': apellidos,
            'nombre_completo': (nombres + ' ' + apellidos).strip(),
            'especialidad': especialidad if especialidad else 'MEDICO ESPECIALISTA',
            'rol': 'RESIDENTE' if 'RESID' in rol else ('ESPECIALISTA' if 'ESPEC' in rol or rol else 'ESPECIALISTA')
        }
    return directory

class LoginDialog(tk.Toplevel):
    def __init__(self, parent, user_dir):
        super().__init__(parent)
        self.title("Inicio de sesión")
        self.resizable(False, False)
        self.user_dir = user_dir
        self.result = None

        frm = ttk.Frame(self, padding=12)
        frm.grid(row=0, column=0)

        ttk.Label(frm, text="Usuario:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        ttk.Label(frm, text="Contraseña (Cédula):").grid(row=1, column=0, sticky="e", padx=6, pady=6)

        self.e_user = ttk.Entry(frm, width=30)
        self.e_pass = ttk.Entry(frm, width=30, show="•")

        self.e_user.grid(row=0, column=1, padx=6, pady=6)
        self.e_pass.grid(row=1, column=1, padx=6, pady=6)

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, pady=(8, 0))
        ttk.Button(btns, text="Ingresar", command=self.on_ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancelar", command=self.on_cancel).pack(side="left", padx=4)

        self.bind("<Return>", lambda e: self.on_ok())
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.grab_set()
        self.e_user.focus()

    def on_ok(self):
        u = normalize_text(self.e_user.get())
        p = self.e_pass.get().strip()
        if u in self.user_dir and str(self.user_dir[u]['password']) == p:
            self.result = self.user_dir[u] | {'username': u}
            self.destroy()
        else:
            messagebox.showerror("Acceso denegado", "Usuario o contraseña inválidos.")

    def on_cancel(self):
        self.result = None
        self.destroy()

class EnhancedApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1200x900")
        
        # Usuario actual (en implementación real vendría de autenticación)
        self.current_user = 'USUARIO_SISTEMA'
        
        # Log inicio de sesión
        log_access(self.current_user, "INICIO_APLICACION", "Aplicación iniciada")
        # Cargar directorio de usuarios y mostrar login
        try:
            excel_path = os.path.join(os.path.dirname(__file__), "LISTADO NOMBRES.xlsx")
            user_dir = load_user_directory(excel_path)
        except Exception as e:
            user_dir = {}
            logger.error(f"Error cargando LISTADO NOMBRES.xlsx: {e}")

        login = LoginDialog(self, user_dir)
        self.wait_window(login)

        if not login.result:
            messagebox.showwarning("Salida", "Debe iniciar sesión para usar la aplicación.")
            self.destroy()
            return

        self.user_info = login.result  # contiene nombres, apellidos, nombre_completo, especialidad, rol, username
        self.current_user = self.user_info.get('nombre_completo', self.current_user)
        log_access(self.current_user, "LOGIN", f"Rol: {self.user_info.get('rol')} - Esp: {self.user_info.get('especialidad')}")
        # Cargar CIE-10 si existe el CSV
        self.cie_index = self.load_cie10()
        self.cie_items = [(c, d) for c, d in (self.cie_index or {}).items()]
        
        # Cargar medicamentos
        self.medicamentos_list = self.load_medicamentos()
        
        self.create_menu()
        self.create_ui()
        
        # Crear respaldo automático al iniciar (una vez al día)
        self.check_and_create_backup()

    def check_and_create_backup(self):
        """Verifica si es necesario crear un respaldo automático"""
        try:
            conn = sqlite3.connect(db_path())
            cur = conn.cursor()
            
            # Verificar último respaldo
            cur.execute("""
                SELECT fecha_respaldo FROM respaldos 
                WHERE tipo_respaldo = 'AUTOMATICO' 
                ORDER BY fecha_respaldo DESC LIMIT 1
            """)
            
            result = cur.fetchone()
            conn.close()
            
            should_backup = True
            if result:
                last_backup = datetime.fromisoformat(result[0])
                today = datetime.now()
                if (today - last_backup).days < 1:
                    should_backup = False
            
            if should_backup:
                create_backup()
                
        except Exception as e:
            logger.error(f"Error verificando respaldos: {e}")

    def create_menu(self):
        """Menú con opciones adicionales de seguridad y auditoría"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # Menú CIE-10
        cie_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="CIE-10", menu=cie_menu)
        cie_menu.add_command(label="Ver Lista Completa", command=self.show_cie10_list)
        cie_menu.add_command(label="Buscar CIE-10", command=self.search_cie10_dialog)
        
        # Menú de Auditoría y Seguridad
        audit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Auditoría", menu=audit_menu)
        audit_menu.add_command(label="Ver Bitácora de Accesos", command=self.show_access_log)
        audit_menu.add_command(label="Ver Auditoría de Recetas", command=self.show_audit_log)
        audit_menu.add_command(label="Crear Respaldo Manual", command=self.manual_backup)
        audit_menu.add_command(label="Verificar Integridad", command=self.verify_integrity)

    def create_ui(self):
        """Crea la interfaz de usuario"""
        nb = ttk.Notebook(self)
        self.tab_form = ttk.Frame(nb)
        self.tab_search = ttk.Frame(nb)
        
        nb.add(self.tab_form, text="Nueva Receta")
        nb.add(self.tab_search, text="Buscar / Reimprimir")
        nb.pack(fill="both", expand=True)

        self.create_form_tab()
        self.create_search_tab()

    def create_form_tab(self):
        """Crea la pestaña del formulario con campos adicionales de seguridad"""
        f = self.tab_form
        for i in range(8):
            f.grid_columnconfigure(i, weight=1)

        row = 0
        
        # Tipo de receta
        self.tipo = tk.StringVar(value="CE")
        ttk.Label(f, text="Tipo:").grid(row=row, column=0, sticky="w", padx=6, pady=6)
        ttk.Radiobutton(
            f, text="Consulta Externa (Azul)", 
            variable=self.tipo, value="CE"
        ).grid(row=row, column=1, sticky="w")
        ttk.Radiobutton(
            f, text="Emergencia (Amarillo)", 
            variable=self.tipo, value="EM"
        ).grid(row=row, column=2, sticky="w")
        ttk.Radiobutton(
            f, text="Hospitalización (Rojo)", 
            variable=self.tipo, value="EH"
        ).grid(row=row, column=3, sticky="w")

        row += 1
        
        # Unidad de salud
        ttk.Label(f, text="Unidad de Salud:").grid(row=row, column=0, sticky="w", padx=6, pady=6)
        self.unidad = tk.Entry(f, width=45)
        self.unidad.insert(0, "HOSPITAL BASICO DE CAYAMBE")
        self.unidad.config(state="readonly")
        self.unidad.grid(row=row, column=1, columnspan=3, sticky="we", padx=6)

        row += 1
        
        # Prescriptor
        ttk.Label(f, text="Prescriptor (firma):").grid(row=row, column=0, sticky="w", padx=6, pady=6)
        self.prescriptor = tk.Entry(f, width=45)
        self.prescriptor.grid(row=row, column=1, columnspan=3, sticky="we", padx=6)

        # NUEVO: Especialidad del prescriptor para validación
        ttk.Label(f, text="Especialidad:").grid(row=row, column=4, sticky="w", padx=6)
        self.prescriptor_especialidad = tk.Entry(f, width=28)
        self.prescriptor_especialidad.grid(row=row, column=5, columnspan=2, sticky="we", padx=6)
        
        # Número de receta (solo lectura)
        ttk.Label(f, text="Número de Receta:").grid(row=row, column=6, sticky="e", padx=6)
        self.numero_var = tk.StringVar(value="(se generará al guardar)")
        self.numero_entry = tk.Entry(f, textvariable=self.numero_var, width=30, state="readonly")
        self.numero_entry.grid(row=row, column=7, sticky="we", padx=6)

        row += 1

        # Separador
        ttk.Separator(f).grid(row=row, column=0, columnspan=8, sticky="ew", pady=6)
        row += 1

        # Datos del paciente
        ttk.Label(f, text="Paciente:").grid(row=row, column=0, sticky="e", padx=6)
        self.paciente = tk.Entry(f, width=40)
        self.paciente.grid(row=row, column=1, columnspan=3, sticky="we", padx=6)
        
        ttk.Label(f, text="CI:").grid(row=row, column=4, sticky="e")
        self.ci = tk.Entry(f, width=20)
        self.ci.grid(row=row, column=5, sticky="w")

        row += 1
        
        ttk.Label(f, text="Historia Clínica:").grid(row=row, column=0, sticky="e", padx=6)
        self.hc = tk.Entry(f, width=30)
        self.hc.grid(row=row, column=1, sticky="we", padx=6)

        ttk.Label(f, text="Sexo:").grid(row=row, column=2, sticky="e")
        self.sexo = ttk.Combobox(f, values=["M", "F"], width=5, state="readonly")
        self.sexo.grid(row=row, column=3, sticky="w")

        ttk.Label(f, text="Edad(años):").grid(row=row, column=4, sticky="e")
        self.edad = tk.Entry(f, width=6, state="readonly")
        self.edad.grid(row=row, column=5, sticky="w")
        
        ttk.Label(f, text="Meses:").grid(row=row, column=6, sticky="e")
        self.meses = tk.Entry(f, width=6, state="readonly")
        self.meses.grid(row=row, column=7, sticky="w", padx=6)

        # Fecha de Nacimiento (dd/mm/aaaa) y cálculo automático
        row += 1
        ttk.Label(f, text="Fecha de Nacimiento (dd/mm/aaaa):").grid(row=row, column=0, sticky="e", padx=6)
        self.fecha_nacimiento = tk.Entry(f, width=16)
        self.fecha_nacimiento.grid(row=row, column=1, sticky="w")
        
        def calc_edad_from_dob(*_):
            from datetime import datetime as _dt
            txt = (self.fecha_nacimiento.get() or "").strip()
            try:
                d = _dt.strptime(txt, "%d/%m/%Y")
                today = _dt.today()
                years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
                months = (today.year - d.year) * 12 + (today.month - d.month)
                if today.day < d.day:
                    months -= 1
                rem_months = months - years*12
                
                try:
                    self.edad.config(state="normal")
                    self.meses.config(state="normal")
                    self.edad.delete(0, "end")
                    self.edad.insert(0, str(max(0, years)))
                    self.meses.delete(0, "end")
                    self.meses.insert(0, str(max(0, rem_months)))
                finally:
                    self.edad.config(state="readonly")
                    self.meses.config(state="readonly")

            except Exception:
                pass
        
        self.fecha_nacimiento.bind("<FocusOut>", calc_edad_from_dob)
        self.fecha_nacimiento.bind("<Return>", calc_edad_from_dob)

        row += 1
        
        ttk.Label(f, text="Talla(cm):").grid(row=row, column=4, sticky="e")
        self.talla = tk.Entry(f, width=6)
        self.talla.grid(row=row, column=5, sticky="w")
        
        ttk.Label(f, text="Peso(kg):").grid(row=row, column=6, sticky="e")
        self.peso = tk.Entry(f, width=6)
        self.peso.grid(row=row, column=7, sticky="w")

        # Separador para campos de salud
        ttk.Separator(f).grid(row=row+1, column=0, columnspan=8, sticky="ew", pady=6)
        row += 2

        # Campos de estado de salud
        ttk.Label(f, text="Actividad Física:").grid(row=row, column=0, sticky="e", padx=6)
        self.actividad_fisica = ttk.Combobox(f, values=["Si", "No", "No aplica"], width=15, state="readonly")
        self.actividad_fisica.grid(row=row, column=1, sticky="w", padx=6)

        ttk.Label(f, text="Estado de Enfermedad:").grid(row=row, column=2, sticky="e", padx=6)
        self.estado_enfermedad = ttk.Combobox(f, values=["Agudo", "Cronico", "No aplica"], width=15, state="readonly")
        self.estado_enfermedad.grid(row=row, column=3, sticky="w", padx=6)

        row += 1

        ttk.Label(f, text="Alergias:").grid(row=row, column=0, sticky="e", padx=6)
        self.alergias = ttk.Combobox(f, values=["Si", "No"], width=10, state="readonly")
        self.alergias.grid(row=row, column=1, sticky="w", padx=6)

        ttk.Label(f, text="Especificar:").grid(row=row, column=2, sticky="e", padx=6)
        self.alergias_especificar = tk.Entry(f, width=40)
        self.alergias_especificar.grid(row=row, column=3, columnspan=3, sticky="we", padx=6)

        # Separador
        ttk.Separator(f).grid(row=row+1, column=0, columnspan=8, sticky="ew", pady=6)
        row += 2

        # CIE-10
        ttk.Label(f, text="CIE-10:").grid(row=row, column=0, sticky="e", padx=6)
        self.cie = tk.Entry(f, width=12)
        self.cie.grid(row=row, column=1, sticky="w")
        
        ttk.Button(f, text="Lista CIE-10", command=self.show_cie10_list, width=12).grid(row=row, column=2, sticky="w", padx=3)
        
        ttk.Label(f, text="Descripción:").grid(row=row, column=3, sticky="e")
        self.cie_desc = tk.Entry(f, width=50)
        self.cie_desc.grid(row=row, column=4, columnspan=4, sticky="we", padx=6)
        
        # Eventos para sugerencias
        self.cie_desc.bind("<KeyRelease>", lambda e: self.show_cie_suggestions(from_desc=True))
        self.cie.bind("<FocusOut>", lambda e: self.autofill_cie_desc())
        self.cie.bind("<Return>", lambda e: self.autofill_cie_desc())
        self.cie.bind("<KeyRelease>", lambda e: self.autofill_cie_desc(partial=True))

        row += 1
        
        # Medicamentos
        ttk.Label(f, text="Medicamentos (sin límite de filas)").grid(
            row=row, column=0, sticky="w", padx=6, pady=(6,0)
        )

        row += 1
        
        cols = ("nombre", "dosis", "frecuencia", "via", "duracion", "cantidad")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=6)
        
        headers = {
            "nombre": "Medicamento (DCI / concentración / forma)",
            "dosis": "Dosis",
            "frecuencia": "Frecuencia",
            "via": "Vía Adm.",
            "duracion": "Duración",
            "cantidad": "Cantidad"
        }
        
        for c in cols:
            self.tree.heading(c, text=headers[c])
            width = 220 if c == "nombre" else 120
            self.tree.column(c, width=width, anchor="w")
            
        self.tree.grid(row=row, column=0, columnspan=8, sticky="nsew", padx=6)
        f.grid_rowconfigure(row, weight=1)

        row += 1
        
        # Campos para agregar medicamentos
        self.m_nombre = tk.Entry(f)
        self.m_dosis = tk.Entry(f, width=10)
        self.m_frec = ttk.Combobox(f, values=["STAT","QD", "BID", "TID", "QUID"], width=10, state="readonly")
        self.m_via = ttk.Combobox(f, values=["ORAL", "INTRAVENOSO", "INTRAMUSCULAR", "SUBCUTANEO", "VAGINAL", "SUBLINGUAL", "TÓPICA", "OFTÁLMICA", "ÓTICA", "INSUMO"], width=12, state="readonly")
        self.m_dur = tk.Entry(f, width=10)
        self.m_cant = tk.Entry(f, width=18)
        
        self.m_nombre.grid(row=row, column=0, columnspan=3, sticky="we", padx=6, pady=3)
        self.m_dosis.grid(row=row, column=3, sticky="w", padx=3)
        self.m_frec.grid(row=row, column=4, sticky="w", padx=3)
        self.m_via.grid(row=row, column=5, sticky="w", padx=3)
        self.m_dur.grid(row=row, column=6, sticky="w", padx=3)
        self.m_cant.grid(row=row, column=7, sticky="we", padx=3)

        # Bind para sugerencias de medicamentos
        self.m_nombre.bind("<KeyRelease>", lambda e: self.show_medicamento_suggestions())

        row += 1
        
        # Botones de medicamentos
        button_frame_med = ttk.Frame(f)
        button_frame_med.grid(row=row, column=0, columnspan=8, sticky="ew", padx=6, pady=3)
        
        ttk.Button(button_frame_med, text="Agregar", command=self.add_med).pack(side="left", padx=(0, 10))
        ttk.Button(button_frame_med, text="Eliminar Seleccionado", command=self.remove_med).pack(side="left", padx=(0, 10))
        ttk.Button(button_frame_med, text="Lista Medicamentos", command=self.show_medicamentos_list).pack(side="left")

        row += 1
        
        # Indicaciones
        ttk.Label(f, text="Indicaciones / Advertencias / Recomendaciones:").grid(
            row=row, column=0, sticky="w", padx=6
        )

        row += 1
        
        self.indicaciones = tk.Text(f, height=6, wrap="word")
        self.indicaciones.grid(row=row, column=0, columnspan=8, sticky="nsew", padx=6, pady=3)
        f.grid_rowconfigure(row, weight=1)

        row += 1
        
        # Botones principales
        button_frame = ttk.Frame(f)
        button_frame.grid(row=row, column=0, columnspan=8, sticky="ew", padx=6, pady=10)
        
        ttk.Button(button_frame, text="Guardar y Generar PDF", command=self.save_and_pdf).pack(
            side="left", padx=(0, 10)
        )

        # Botón adicional para imprimir solo INDICACIONES
        def imprimir_indicaciones():
            try:
                data = self.collect_form()
                data["fecha_nacimiento"] = getattr(self, "fecha_nacimiento", tk.Entry()).get() if hasattr(self, "fecha_nacimiento") else ""
                from pdf_layout_fixed import build_indicaciones_pdf
                output_dir = DEFAULT_OUTPUT
                os.makedirs(output_dir, exist_ok=True)
                nombre_pdf = (self.numero_var.get() or "INDICACIONES") + "_indicaciones.pdf"
                out_path = os.path.join(output_dir, nombre_pdf)
                build_indicaciones_pdf(out_path, data)
                open_file_cross_platform(out_path)
                messagebox.showinfo("Indicaciones", f"PDF de indicaciones generado: {out_path}")
            except Exception as e:
                messagebox.showerror("Indicaciones", f"No se pudo generar indicaciones: {e}")

        ttk.Button(button_frame, text="Imprimir Indicaciones", command=imprimir_indicaciones).pack(side="left", padx=(10,0))
        ttk.Button(button_frame, text="Limpiar", command=self.clear_form).pack(side="left")

        # Ajustes según rol del usuario autenticado
        try:
            rol = (self.user_info.get("rol","")).upper()
            esp = (self.user_info.get("especialidad","") or "").upper().strip()
            nombre_comp = self.user_info.get("nombre_completo","")

            # Prescriptor: nombre y apellidos completos (readonly)
            self.prescriptor.delete(0, "end")
            self.prescriptor.insert(0, nombre_comp)
            self.prescriptor.config(state="readonly")

            # Set especialidad en el campo y bloquear edición
            try:
                self.prescriptor_especialidad.delete(0, "end")
                self.prescriptor_especialidad.insert(0, esp if esp else "MEDICO ESPECIALISTA")
                self.prescriptor_especialidad.config(state="readonly")
            except Exception as _e:
                logger.warning(f"No se pudo fijar especialidad: {_e}")

            # Restricciones por rol
            if rol == "RESIDENTE":
                # Tipo: solo EM (amarillo) y EH (rojo) -> deshabilitar CE
                for child in f.grid_slaves():
                    if isinstance(child, ttk.Radiobutton) and "Consulta Externa" in str(child.cget("text")):
                        child.state(["disabled"])
                # No hay servicio; especialidad queda fija del usuario
            else:
                # ESPECIALISTA: puede CE/EM/EH
                pass

        except Exception as e:
            logger.error(f"Error aplicando restricciones por rol: {e}")

    def create_search_tab(self):
        """Crea la pestaña de búsqueda"""
        s = self.tab_search
        
        ttk.Label(s, text="Número de receta:").grid(row=0, column=0, padx=6, pady=6, sticky="e")
        self.search_num = tk.Entry(s, width=30)
        self.search_num.grid(row=0, column=1, sticky="w")
        
        ttk.Button(s, text="Abrir PDF", command=self.open_pdf).grid(row=0, column=2, padx=6)
        ttk.Button(s, text="Exportar CSV", command=self.export_csv).grid(row=0, column=3, padx=6)
        
        self.result_label = ttk.Label(s, text="")
        self.result_label.grid(row=1, column=0, columnspan=4, sticky="w", padx=6)

    def load_medicamentos(self):
        """Carga la lista de medicamentos desde el CSV"""
        medicamentos = []
        try:
            if not os.path.exists(MEDICAMENTOS_CSV):
                logger.warning(f"Archivo de medicamentos no encontrado: {MEDICAMENTOS_CSV}")
                return medicamentos
            
            try:
                df = pd.read_csv(MEDICAMENTOS_CSV, sep='|')
                if 'nombre' in df.columns:
                    medicamentos = df['nombre'].dropna().tolist()
                else:
                    medicamentos = df.iloc[:, 0].dropna().tolist()
            except:
                with open(MEDICAMENTOS_CSV, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f, delimiter='|')
                    for row in reader:
                        if row and len(row) > 0:
                            medicamento = row[0].strip()
                            if medicamento and not medicamento.startswith('nombre'):
                                medicamentos.append(medicamento)
            
            logger.info(f"Medicamentos cargados: {len(medicamentos)}")
            return medicamentos
            
        except Exception as e:
            logger.error(f"Error cargando medicamentos: {e}")
            return []

    def load_cie10(self):
        """Carga el CSV de CIE-10 en un diccionario {CODE: DESC}"""
        idx = {}
        try:
            if not os.path.exists(CIE10_CSV):
                logger.warning(f"Archivo CIE-10 no encontrado: {CIE10_CSV}")
                return idx
                
            with open(CIE10_CSV, 'r', encoding='utf-8') as f:
                content = f.read()
                
            cie_pattern = r'\b([A-Z]\d{2}(?:\.\d+)?)\b'
            lines = content.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                matches = re.findall(cie_pattern, line)
                
                for code in matches:
                    code_pos = line.find(code)
                    if code_pos != -1:
                        desc_start = code_pos + len(code)
                        desc = line[desc_start:].strip()
                        desc = re.sub(r'^[^\w]*', '', desc)
                        desc = desc.split('  ')[0]
                        
                        if desc and len(desc) > 3:
                            idx[code.upper()] = desc[:200]
            
            if not idx:
                try:
                    with open(CIE10_CSV, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            code = (row.get('code') or row.get('codigo') or '').strip().upper()
                            desc = (row.get('desc') or row.get('descripcion') or '').strip()
                            if code and desc:
                                idx[code] = desc
                except:
                    pass
            
            if not idx:
                common_codes = {
                    'Z00.0': 'Examen médico general',
                    'Z51.1': 'Quimioterapia para neoplasia',
                    'I10': 'Hipertensión esencial (primaria)',
                    'E11': 'Diabetes mellitus no insulinodependiente',
                    'J06.9': 'Infección aguda de las vías respiratorias superiores, no especificada',
                    'K59.0': 'Estreñimiento',
                    'M79.3': 'Paniculitis, no especificada',
                    'R50.9': 'Fiebre, no especificada',
                    'R06.0': 'Disnea',
                    'R51': 'Cefalea'
                }
                idx.update(common_codes)
                
            logger.info(f"CIE-10: Cargados {len(idx)} códigos")
            
        except Exception as e:
            logger.error(f"Error cargando CIE-10: {e}")
            messagebox.showwarning("CIE-10", f"Error al cargar catálogo CIE-10: {e}")
            
        return idx

    def show_cie10_list(self):
        """Muestra una ventana con la lista completa de códigos CIE-10 - FIXED"""
        if not self.cie_index:
            messagebox.showinfo("CIE-10", "No se ha cargado el catálogo CIE-10")
            return
            
        cie_window = tk.Toplevel(self)
        cie_window.title("Lista de Códigos CIE-10")
        cie_window.geometry("900x600")
        
        main_frame = ttk.Frame(cie_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text="Buscar:").pack(side="left")
        search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=search_var, width=50)
        search_entry.pack(side="left", padx=(5, 10))
        
        columns = ("codigo", "descripcion")
        tree = ttk.Treeview(main_frame, columns=columns, show="headings", height=20)
        
        tree.heading("codigo", text="Código CIE-10")
        tree.heading("descripcion", text="Descripción")
        
        tree.column("codigo", width=120, anchor="w")
        tree.column("descripcion", width=600, anchor="w")
        
        v_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=tree.yview)
        h_scrollbar = ttk.Scrollbar(main_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        tree.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")
        
        def filter_list():
            search_text = search_var.get().lower()
            tree.delete(*tree.get_children())
            
            for code, desc in sorted(self.cie_index.items()):
                if (search_text in code.lower() or 
                    search_text in desc.lower()):
                    tree.insert("", "end", values=(code, desc))
        
        def select_code(event):
            selection = tree.selection()
            if selection:
                item = tree.item(selection[0])
                code, desc = item['values']
                
                self.cie.delete(0, "end")
                self.cie.insert(0, code)
                self.cie_desc.delete(0, "end")
                self.cie_desc.insert(0, desc)
                
                cie_window.destroy()
        
        search_entry.bind("<KeyRelease>", lambda e: filter_list())
        tree.bind("<Double-1>", select_code)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="Seleccionar", 
                  command=lambda: select_code(None) if tree.selection() else None).pack(side="left")
        ttk.Button(button_frame, text="Cerrar", 
                  command=cie_window.destroy).pack(side="right")
        
        filter_list()
        search_entry.focus()

    def show_medicamentos_list(self):
        """Muestra una ventana con la lista completa de medicamentos - FIXED"""
        if not self.medicamentos_list:
            messagebox.showinfo("Medicamentos", "No se ha cargado el catálogo de medicamentos")
            return
            
        med_window = tk.Toplevel(self)
        med_window.title("Lista de Medicamentos Disponibles")
        med_window.geometry("1000x600")
        
        main_frame = ttk.Frame(med_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text="Buscar:").pack(side="left")
        search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=search_var, width=60)
        search_entry.pack(side="left", padx=(5, 10))
        
        listbox_frame = ttk.Frame(main_frame)
        listbox_frame.pack(fill="both", expand=True)
        
        listbox = tk.Listbox(listbox_frame, width=120, height=25)
        scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        def filter_list():
            search_text = search_var.get().lower()
            listbox.delete(0, tk.END)
            
            for medicamento in self.medicamentos_list:
                if search_text in medicamento.lower():
                    listbox.insert(tk.END, medicamento)
        
        def select_medicamento(event=None):
            selection = listbox.curselection()
            if selection:
                medicamento = listbox.get(selection[0])
                
                self.m_nombre.delete(0, "end")
                self.m_nombre.insert(0, medicamento)
                
                med_window.destroy()
        
        search_entry.bind("<KeyRelease>", lambda e: filter_list())
        listbox.bind("<Double-1>", select_medicamento)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="Seleccionar", 
                  command=select_medicamento).pack(side="left")
        ttk.Button(button_frame, text="Cerrar", 
                  command=med_window.destroy).pack(side="right")
        
        filter_list()
        search_entry.focus()

    def show_medicamento_suggestions(self):
        """Muestra sugerencias de medicamentos mientras se escribe - FIXED"""
        try:
            query = self.m_nombre.get().lower().strip()
            if len(query) < 3:
                self.hide_medicamento_suggestions()
                return
            
            matches = [med for med in self.medicamentos_list if query in med.lower()]
            matches = matches[:10]
            
            if not matches:
                self.hide_medicamento_suggestions()
                return
            
            if not hasattr(self, '_med_win') or not self._med_win or not self._med_win.winfo_exists():
                self._med_win = tk.Toplevel(self)
                self._med_win.overrideredirect(True)
                self._med_list = tk.Listbox(self._med_win, height=8, width=100)
                self._med_list.pack(fill='both', expand=True)
                self._med_list.bind('<Double-Button-1>', lambda e: self.pick_medicamento_suggestion())
                self._med_list.bind('<Return>', lambda e: self.pick_medicamento_suggestion())
            else:
                self._med_list.delete(0, 'end')
            
            for med in matches:
                self._med_list.insert('end', med)
            
            x = self.m_nombre.winfo_rootx()
            y = self.m_nombre.winfo_rooty() + self.m_nombre.winfo_height()
            self._med_win.geometry(f"800x160+{x}+{y}")
            self._med_win.deiconify()
            
        except Exception:
            pass

    def hide_medicamento_suggestions(self):
        try:
            if hasattr(self, '_med_win') and self._med_win and self._med_win.winfo_exists():
                self._med_win.withdraw()
        except Exception:
            pass

    def pick_medicamento_suggestion(self):
        """Toma el medicamento seleccionado y llena el campo"""
        try:
            if not hasattr(self, '_med_list'):
                return
            sel = self._med_list.curselection()
            if not sel:
                return
            medicamento = self._med_list.get(sel[0])
            self.m_nombre.delete(0, 'end')
            self.m_nombre.insert(0, medicamento)
            self.hide_medicamento_suggestions()
        except Exception:
            pass

    def autofill_cie_desc(self, partial=False):
        """Autorrellena la descripción desde el catálogo CIE-10 - FIXED"""
        code = (self.cie.get() or '').strip().upper()
        if not code or (partial and len(code) < 3):
            return self.show_cie_suggestions()
        if hasattr(self, 'cie_index') and self.cie_index:
            desc = self.cie_index.get(code)
            if desc:
                try:
                    self.cie_desc.delete(0, 'end')
                    self.cie_desc.insert(0, desc)
                except Exception:
                    pass
        self.show_cie_suggestions()

    def show_cie_suggestions(self, from_desc: bool=False):
        """Muestra un menú flotante de sugerencias (código + descripción) - FIXED"""
        try:
            if not self.cie_items:
                return
            if from_desc:
                q = (self.cie_desc.get() or '').strip().lower()
                if len(q) < 3:
                    self.hide_cie_suggestions(); return
                def match(item):
                    c, d = item; return q in (d or '').lower()
            else:
                q = (self.cie.get() or '').strip().upper()
                if len(q) < 1:
                    self.hide_cie_suggestions(); return
                def match(item):
                    c, d = item; return c.startswith(q)
            results = [it for it in self.cie_items if match(it)]
            results = results[:12]
            if not results:
                self.hide_cie_suggestions(); return

            if not hasattr(self, '_cie_win') or not self._cie_win or not self._cie_win.winfo_exists():
                self._cie_win = tk.Toplevel(self)
                self._cie_win.overrideredirect(True)
                self._cie_list = tk.Listbox(self._cie_win, height=8, width=80)
                self._cie_list.pack(fill='both', expand=True)
                self._cie_list.bind('<Double-Button-1>', lambda e: self.pick_cie_suggestion())
                self._cie_list.bind('<Return>', lambda e: self.pick_cie_suggestion())
            else:
                self._cie_list.delete(0, 'end')

            for c, d in results:
                self._cie_list.insert('end', f"{c} — {d}")

            widget = self.cie_desc if from_desc else self.cie
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height()
            self._cie_win.geometry(f"600x160+{x}+{y}")
            self._cie_win.deiconify()
        except Exception:
            pass

    def hide_cie_suggestions(self):
        try:
            if hasattr(self, '_cie_win') and self._cie_win and self._cie_win.winfo_exists():
                self._cie_win.withdraw()
        except Exception:
            pass

    def pick_cie_suggestion(self):
        """Toma el seleccionado y llena código y descripción."""
        try:
            if not hasattr(self, '_cie_list'):
                return
            sel = self._cie_list.curselection()
            if not sel:
                return
            text = self._cie_list.get(sel[0])
            if '—' in text:
                code, desc = text.split('—', 1)
                code = code.strip(); desc = desc.strip()
                self.cie.delete(0, 'end'); self.cie.insert(0, code)
                self.cie_desc.delete(0, 'end'); self.cie_desc.insert(0, desc)
            self.hide_cie_suggestions()
        except Exception:
            pass

    def search_cie10_dialog(self):
        """Abre un diálogo de búsqueda rápida de CIE-10 - FIXED"""
        if not self.cie_index:
            messagebox.showinfo("CIE-10", "No se ha cargado el catálogo CIE-10")
            return
            
        search_text = simpledialog.askstring("Buscar CIE-10", 
                                           "Ingrese código o descripción a buscar:")
        if not search_text:
            return
            
        search_text = search_text.lower()
        results = []
        
        for code, desc in self.cie_index.items():
            if (search_text in code.lower() or 
                search_text in desc.lower()):
                results.append((code, desc))
                
        if not results:
            messagebox.showinfo("Búsqueda", "No se encontraron resultados")
            return
            
        if len(results) == 1:
            code, desc = results[0]
            self.cie.delete(0, "end")
            self.cie.insert(0, code)
            self.cie_desc.delete(0, "end")
            self.cie_desc.insert(0, desc)
            messagebox.showinfo("CIE-10", f"Código seleccionado: {code}")
        else:
            result_window = tk.Toplevel(self)
            result_window.title(f"Resultados de búsqueda: {len(results)} encontrados")
            result_window.geometry("800x400")
            
            listbox = tk.Listbox(result_window, width=100, height=20)
            listbox.pack(fill="both", expand=True, padx=10, pady=10)
            
            for code, desc in results[:50]:
                listbox.insert("end", f"{code} - {desc}")
                
            def select_result():
                selection = listbox.curselection()
                if selection:
                    selected_text = listbox.get(selection[0])
                    code = selected_text.split(" - ")[0]
                    desc = " - ".join(selected_text.split(" - ")[1:])
                    
                    self.cie.delete(0, "end")
                    self.cie.insert(0, code)
                    self.cie_desc.delete(0, "end")
                    self.cie_desc.insert(0, desc)
                    
                    result_window.destroy()
            
            button_frame = ttk.Frame(result_window)
            button_frame.pack(fill="x", padx=10, pady=5)
            
            ttk.Button(button_frame, text="Seleccionar", command=select_result).pack(side="left")
            ttk.Button(button_frame, text="Cerrar", command=result_window.destroy).pack(side="right")
            
            listbox.bind("<Double-1>", lambda e: select_result())

    def validate(self, data):
        """Valida los datos del formulario con validaciones adicionales de seguridad"""
        # Campos requeridos
        required_fields = [
            ("Paciente", data["paciente"]),
            ("CI", data["ci"]),
            ("CIE-10", data["cie"]),
            ("Prescriptor", data["prescriptor"]),
            ("Especialidad del Prescriptor", data.get("prescriptor_especialidad", ""))
        ]
        
        for label, val in required_fields:
            if not (val or "").strip():
                messagebox.showerror("Campo requerido", f"Falta: {label}")
                return False
        
        # Validar CI
        if not validate_ci(data["ci"]):
            messagebox.showerror("Validación", "CI no válida (mínimo 10 caracteres alfanuméricos)")
            return False
        
        # NUEVA VALIDACIÓN: Correspondencia profesional-servicio
        if not validate_professional_service(data["servicio"], data.get("prescriptor_especialidad", "")):
            messagebox.showerror(
                "Validación Profesional", 
                f"La especialidad '{data.get('prescriptor_especialidad', '')}' no está autorizada para el servicio '{data['servicio']}'"
            )
            return False
        
        # Validar campos numéricos
        if data["edad"] and not validate_numeric(data["edad"], "Edad", 0, 150):
            return False
            
        if data["meses"] and not validate_numeric(data["meses"], "Meses", 0, 11):
            return False
            
        if data["talla"] and not validate_numeric(data["talla"], "Talla", 0, 300):
            return False
            
        if data["peso"] and not validate_numeric(data["peso"], "Peso", 0, 1000):
            return False
        
        # Validar medicamentos
        if len(data["meds"]) == 0:
            messagebox.showerror("Medicamentos", "Agregue al menos un medicamento.")
            return False
        
        # Si tenemos catálogo CIE-10 y el código existe, aseguramos descripción estándar
        if hasattr(self, 'cie_index') and self.cie_index and data["cie"]:
            desc = self.cie_index.get(data["cie"].strip().upper())
            if desc:
                data["cie_desc"] = desc
                try:
                    self.cie_desc.delete(0, "end")
                    self.cie_desc.insert(0, desc)
                except Exception:
                    pass
        
        return True

    def save_and_pdf(self):
        """Guarda la receta y genera el PDF con trazabilidad completa"""
        data = self.collect_form()
        if not self.validate(data):
            return
            
        if not ensure_db():
            return
            
        try:
            # Generar número al momento de guardar
            numero = next_number(data["tipo"])
            if not numero:
                return
                
            data["numero"] = numero
            data["prescriptor_especialidad"] = self.prescriptor_especialidad.get()

            # Mostrar el número en la interfaz
            try:
                self.numero_var.set(numero)
            except Exception:
                pass
            
            # Crear directorio de salida
            output_dir = DEFAULT_OUTPUT
            os.makedirs(output_dir, exist_ok=True)
            out_path = os.path.join(output_dir, f"{numero}.pdf")
            
            # Generar PDF
            try:
                build_pdf(out_path, data, tipo=data["tipo"])            
            except Exception as pdf_error:
                logger.error(f"Error generando PDF: {pdf_error}")
                messagebox.showerror("Error PDF", f"Error al generar PDF: {str(pdf_error)}")
                return
            
            # ENHANCED: Calcular hash para integridad
            data_hash = calculate_hash(data)
            
            # Guardar en base de datos con campos adicionales de seguridad
            conn = sqlite3.connect(db_path())
            cur = conn.cursor()
            
            cur.execute("""
                INSERT INTO recetas (
                    id, numero, tipo, fecha, unidad, servicio, prescriptor, prescriptor_especialidad,
                    paciente, ci, hc, edad, meses, sexo, talla, peso,
                    cie, cie_desc, indicaciones, actividad_fisica, estado_enfermedad,
                    alergias, alergias_especificar, payload, pdf_path,
                    created_at, created_by, ip_address, hash_verificacion, estado
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(uuid.uuid4()), numero, data["tipo"], data["fecha"], 
                data["unidad"], data["servicio"], data["prescriptor"], data["prescriptor_especialidad"],
                data["paciente"], data["ci"], data["hc"], data["edad"], 
                data["meses"], data.get("sexo", ""), data["talla"], data["peso"],
                data["cie"], data["cie_desc"], data["indicaciones"],
                data["actividad_fisica"], data["estado_enfermedad"],
                data["alergias"], data["alergias_especificar"],
                json.dumps(data, ensure_ascii=False), out_path,
                datetime.now().isoformat(), self.current_user, get_local_ip(), data_hash, "ACTIVA"
            ))
            
            conn.commit()
            conn.close()
            
            # ENHANCED: Registrar en auditoría
            log_audit(numero, "CREACION", self.current_user, f"Receta creada para paciente {data['paciente']}", "", data_hash)
            
            # Log acceso
            log_access(self.current_user, "CREAR_RECETA", f"Receta {numero} creada exitosamente", "EXITOSO")
            
            messagebox.showinfo(
                "Receta", 
                f"Receta guardada con trazabilidad completa.\nNúmero: {numero}\nPDF: {out_path}"
            )

            # Intentar abrir el PDF
            open_file_cross_platform(out_path)
                
        except Exception as e:
            logger.error(f"Error guardando receta: {e}")
            log_access(self.current_user, "CREAR_RECETA", f"Error: {str(e)}", "ERROR")
            messagebox.showerror("Error", f"Error al guardar la receta: {str(e)}")

    def collect_form(self):
        """Recolecta los datos del formulario"""
        meds = []
        for iid in self.tree.get_children():
            v = self.tree.item(iid, "values")
            meds.append({
                "nombre": v[0],
                "dosis": v[1],
                "frecuencia": v[2],
                "via": v[3],
                "duracion": v[4],
                "cantidad": v[5]
            })
            
        return {
            "tipo": self.tipo.get(),
            "unidad": self.unidad.get(),
            "servicio": getattr(self.prescriptor_especialidad, 'get', lambda: '')(),
            "prescriptor": self.prescriptor.get(),
            "prescriptor_especialidad": self.prescriptor_especialidad.get(),
            "paciente": self.paciente.get(),
            "ci": self.ci.get(),
            "hc": self.hc.get(),
            "edad": self.edad.get(),
            "meses": self.meses.get(),
            "sexo": self.sexo.get() if hasattr(self.sexo, 'get') else '',
            "talla": self.talla.get(),
            "peso": self.peso.get(),
            "cie": self.cie.get(),
            "cie_desc": self.cie_desc.get(),
            "indicaciones": self.indicaciones.get("1.0", "end").strip(),
            "actividad_fisica": self.actividad_fisica.get(),
            "estado_enfermedad": self.estado_enfermedad.get(),
            "alergias": self.alergias.get(),
            "alergias_especificar": self.alergias_especificar.get(),
            "meds": meds,
            "fecha": datetime.now().strftime("%d/%m/%Y"),
            "fecha_nacimiento": getattr(self, "fecha_nacimiento", tk.Entry()).get() if hasattr(self, "fecha_nacimiento") else ""
        }

    # Métodos de auditoría y seguridad
    def show_access_log(self):
        """Muestra la bitácora de accesos"""
        try:
            conn = sqlite3.connect(db_path())
            cur = conn.cursor()
            cur.execute("""
                SELECT fecha_hora, usuario, accion, ip_address, resultado, detalles
                FROM bitacora_accesos 
                ORDER BY fecha_hora DESC LIMIT 100
            """)
            rows = cur.fetchall()
            conn.close()
            
            # Crear ventana para mostrar log
            log_window = tk.Toplevel(self)
            log_window.title("Bitácora de Accesos")
            log_window.geometry("1000x600")
            
            # Crear Treeview
            columns = ("fecha_hora", "usuario", "accion", "ip", "resultado", "detalles")
            tree = ttk.Treeview(log_window, columns=columns, show="headings", height=25)
            
            headers = {
                "fecha_hora": "Fecha/Hora",
                "usuario": "Usuario", 
                "accion": "Acción",
                "ip": "IP",
                "resultado": "Resultado",
                "detalles": "Detalles"
            }
            
            for col in columns:
                tree.heading(col, text=headers[col])
                tree.column(col, width=150 if col == "detalles" else 120)
            
            # Insertar datos
            for row in rows:
                tree.insert("", "end", values=row)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(log_window, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            
            tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
            scrollbar.pack(side="right", fill="y", pady=10)
            
            log_access(self.current_user, "VER_BITACORA_ACCESOS", "Consulta de bitácora de accesos")
            
        except Exception as e:
            logger.error(f"Error mostrando bitácora: {e}")
            messagebox.showerror("Error", f"Error al mostrar bitácora: {str(e)}")

    def show_audit_log(self):
        """Muestra la auditoría de recetas"""
        try:
            conn = sqlite3.connect(db_path())
            cur = conn.cursor()
            cur.execute("""
                SELECT fecha_hora, receta_numero, accion, usuario, ip_address, detalles
                FROM auditoria 
                ORDER BY fecha_hora DESC LIMIT 100
            """)
            rows = cur.fetchall()
            conn.close()
            
            # Crear ventana para mostrar auditoría
            audit_window = tk.Toplevel(self)
            audit_window.title("Auditoría de Recetas")
            audit_window.geometry("1000x600")
            
            # Crear Treeview
            columns = ("fecha_hora", "receta", "accion", "usuario", "ip", "detalles")
            tree = ttk.Treeview(audit_window, columns=columns, show="headings", height=25)
            
            headers = {
                "fecha_hora": "Fecha/Hora",
                "receta": "Receta",
                "accion": "Acción", 
                "usuario": "Usuario",
                "ip": "IP",
                "detalles": "Detalles"
            }
            
            for col in columns:
                tree.heading(col, text=headers[col])
                tree.column(col, width=150 if col == "detalles" else 120)
            
            # Insertar datos
            for row in rows:
                tree.insert("", "end", values=row)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(audit_window, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            
            tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
            scrollbar.pack(side="right", fill="y", pady=10)
            
            log_access(self.current_user, "VER_AUDITORIA_RECETAS", "Consulta de auditoría de recetas")
            
        except Exception as e:
            logger.error(f"Error mostrando auditoría: {e}")
            messagebox.showerror("Error", f"Error al mostrar auditoría: {str(e)}")

    def manual_backup(self):
        """Crea un respaldo manual"""
        try:
            if create_backup():
                messagebox.showinfo("Respaldo", "Respaldo creado exitosamente")
                log_access(self.current_user, "CREAR_RESPALDO", "Respaldo manual creado")
            else:
                messagebox.showerror("Error", "Error al crear respaldo")
        except Exception as e:
            logger.error(f"Error en respaldo manual: {e}")
            messagebox.showerror("Error", f"Error al crear respaldo: {str(e)}")

    def verify_integrity(self):
        """Verifica la integridad de las recetas"""
        try:
            conn = sqlite3.connect(db_path())
            cur = conn.cursor()
            cur.execute("SELECT numero, payload, hash_verificacion FROM recetas WHERE estado = 'ACTIVA'")
            rows = cur.fetchall()
            conn.close()
            
            corrupted = []
            verified = 0
            
            for numero, payload_str, stored_hash in rows:
                try:
                    if payload_str and stored_hash:
                        payload = json.loads(payload_str)
                        calculated_hash = calculate_hash(payload)
                        
                        if calculated_hash != stored_hash:
                            corrupted.append(numero)
                        else:
                            verified += 1
                except Exception:
                    corrupted.append(numero)
            
            if corrupted:
                messagebox.showwarning(
                    "Verificación de Integridad",
                    f"ATENCIÓN: Se encontraron {len(corrupted)} recetas con posibles alteraciones:\n" +
                    "\n".join(corrupted[:10]) + 
                    ("\n..." if len(corrupted) > 10 else "")
                )
            else:
                messagebox.showinfo(
                    "Verificación de Integridad",
                    f"Verificación completada exitosamente.\n{verified} recetas verificadas sin problemas."
                )

            log_access(self.current_user, "VERIFICAR_INTEGRIDAD", f"Verificadas {verified} recetas, {len(corrupted)} con problemas")
            
        except Exception as e:
            logger.error(f"Error verificando integridad: {e}")
            messagebox.showerror("Error", f"Error al verificar integridad: {str(e)}")

    def add_med(self):
        """Agrega un medicamento a la lista"""
        vals = [
            self.m_nombre.get(),
            self.m_dosis.get(),
            self.m_frec.get(),
            self.m_via.get(),
            self.m_dur.get(),
            self.m_cant.get()
        ]
        
        if not vals[0].strip():
            messagebox.showwarning(
                "Medicamento",
                "Ingrese al menos el nombre (DCI / concentración / forma)."
            )
            return
            
        self.tree.insert("", "end", values=vals)
        
        # Limpiar campos
        self.m_nombre.delete(0, "end")
        self.m_dosis.delete(0, "end")
        self.m_frec.set("")
        self.m_via.set("")
        self.m_dur.delete(0, "end")
        self.m_cant.delete(0, "end")

    def remove_med(self):
        """Elimina el medicamento seleccionado de la lista"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Medicamento", "Seleccione un medicamento para eliminar.")
            return
        
        for item in selected:
            self.tree.delete(item)

    def clear_form(self):
        """Limpia el formulario"""
        if messagebox.askyesno("Confirmar", "¿Está seguro de que desea limpiar el formulario?"):
            fields = [
                self.prescriptor, self.paciente, self.ci, self.hc, 
                self.edad, self.meses, self.talla, self.peso, 
                self.cie, self.cie_desc, self.alergias_especificar
            ]
            
            for w in fields:
                w.delete(0, "end")
                
            try:
                self.sexo.set("")
                self.prescriptor_especialidad.set("")
                self.actividad_fisica.set("")
                self.estado_enfermedad.set("")
                self.alergias.set("")
            except Exception:
                pass
                
            for child in self.tree.get_children():
                self.tree.delete(child)
                
            self.indicaciones.delete("1.0", "end")

            try:
                self.numero_var.set("(se generará al guardar)")
            except Exception:
                pass

    def open_pdf(self):
        """Abre un PDF de receta existente con registro de auditoría"""
        num = self.search_num.get().strip()
        if not num:
            messagebox.showwarning("Buscar", "Ingrese número (ej. CE-2025-000000).")
            return
            
        if not ensure_db():
            return
            
        try:
            conn = sqlite3.connect(db_path())
            cur = conn.cursor()
            cur.execute("SELECT pdf_path, estado FROM recetas WHERE numero=?", (num,))
            row = cur.fetchone()
            conn.close()
            
            if not row:
                self.result_label.config(text="No encontrado.")
                log_access(self.current_user, "BUSCAR_RECETA", f"Receta {num} no encontrada", "NO_ENCONTRADO")
                return
                
            path, estado = row
            self.result_label.config(text=f"Abrir: {path} (Estado: {estado})")
            
            if not os.path.exists(path):
                messagebox.showerror("Error", f"El archivo PDF no existe: {path}")
                return
            
            # Registrar acceso a la receta
            log_audit(num, "CONSULTA", self.current_user, f"PDF consultado desde {get_local_ip()}")
            log_access(self.current_user, "ABRIR_PDF", f"PDF {num} abierto", "EXITOSO")
                
            open_file_cross_platform(path)
                
        except Exception as e:
            logger.error(f"Error buscando receta: {e}")
            log_access(self.current_user, "BUSCAR_RECETA", f"Error: {str(e)}", "ERROR")
            messagebox.showerror("Error", f"Error al buscar la receta: {str(e)}")

    def export_csv(self):
        """Exporta las recetas a CSV con registro de auditoría"""
        if not ensure_db():
            return
            
        try:
            conn = sqlite3.connect(db_path())
            cur = conn.cursor()
            cur.execute("""
                SELECT numero, tipo, fecha, paciente, ci, cie, cie_desc, pdf_path, estado, created_by
                FROM recetas 
                ORDER BY fecha DESC
            """)
            rows = cur.fetchall()
            conn.close()
            
            if not rows:
                messagebox.showinfo("Exportar", "No hay recetas para exportar.")
                return
            
            os.makedirs(DEFAULT_OUTPUT, exist_ok=True)
            out = os.path.join(DEFAULT_OUTPUT, f"recetas_export_{int(datetime.now().timestamp())}.csv")
            
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["numero", "tipo", "fecha", "paciente", "ci", "cie", "cie_desc", "pdf_path", "estado", "created_by"])
                w.writerows(rows)
            
            log_access(self.current_user, "EXPORTAR_CSV", f"Exportadas {len(rows)} recetas a {out}")
            messagebox.showinfo("CSV", f"Exportado: {out}")
            
        except Exception as e:
            logger.error(f"Error exportando CSV: {e}")
            log_access(self.current_user, "EXPORTAR_CSV", f"Error: {str(e)}", "ERROR")
            messagebox.showerror("Error", f"Error al exportar CSV: {str(e)}")

if __name__ == "__main__":
    if ensure_db():
        app = EnhancedApp()
        app.mainloop()
    else:
        messagebox.showerror("Error", "No se pudo inicializar la base de datos")
