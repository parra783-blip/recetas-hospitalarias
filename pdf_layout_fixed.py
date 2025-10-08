"""
PDF Layout module for generating prescription PDFs using fpdf2
Supports different prescription types with color-coded headers
Fixed version with proper text wrapping for medications
"""

from fpdf import FPDF
import os
from datetime import datetime

def build_pdf(output_path, data, tipo="CE"):
    """
    Builds a PDF prescription with the given data
    
    Args:
        output_path: Path where to save the PDF
        data: Dictionary with prescription data
        tipo: Type of prescription (CE, EM, EH)
    """
    
    # Color mapping for different prescription types
    colors = {
        "CE": (0, 100, 200),    # Blue for Consulta Externa
        "EM": (255, 193, 7),    # Yellow for Emergencia  
        "EH": (220, 53, 69)     # Red for Hospitalización
    }
    
    # Get color for this prescription type
    header_color = colors.get(tipo, (0, 100, 200))
    
    class PDF(FPDF):
        def header(self):
            # Hospital header with colored background
            self.set_fill_color(*header_color)
            self.rect(0, 0, 210, 25, 'F')
            
            # White text on colored background
            self.set_text_color(255, 255, 255)
            self.set_font('Arial', 'B', 16)
            self.cell(0, 10, 'HOSPITAL BÁSICO DE CAYAMBE', 0, 1, 'C')
            self.set_font('Arial', 'B', 12)
            self.cell(0, 8, 'RECETA MÉDICA ELECTRÓNICA', 0, 1, 'C')
            
            # Reset text color to black
            self.set_text_color(0, 0, 0)
            self.ln(5)
        
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

        def wrap_text(self, text, width):
            """Wrap text to fit within specified width"""
            if not text:
                return ['']
            
            words = str(text).split()
            lines = []
            current_line = ""
            
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if self.get_string_width(test_line) <= width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                        current_line = word
                    else:
                        # Word is too long, break it
                        lines.append(word[:20] + "...")
                        current_line = ""
            
            if current_line:
                lines.append(current_line)
            
            return lines if lines else ['']

        def multi_cell_table(self, data_list, widths, height=6):
            """Create a table with multi-line cells"""
            if not data_list:
                return
            
            # Calculate maximum lines needed for each row
            for row_data in data_list:
                max_lines = 1
                wrapped_cells = []
                
                for i, (cell_data, width) in enumerate(zip(row_data, widths)):
                    wrapped_text = self.wrap_text(cell_data, width - 2)  # -2 for padding
                    wrapped_cells.append(wrapped_text)
                    max_lines = max(max_lines, len(wrapped_text))
                
                # Draw the row with proper height
                row_height = height * max_lines
                start_y = self.get_y()
                
                # Draw cells
                for i, (wrapped_text, width) in enumerate(zip(wrapped_cells, widths)):
                    x_pos = 10 + sum(widths[:i])  # Calculate x position
                    
                    # Draw cell border
                    self.rect(x_pos, start_y, width, row_height)
                    
                    # Add text line by line
                    for j, line in enumerate(wrapped_text):
                        self.set_xy(x_pos + 1, start_y + (j * height) + 1)
                        self.cell(width - 2, height - 1, line, 0, 0, 'L')
                
                # Move to next row
                self.set_y(start_y + row_height)

    # Create PDF instance
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 10)
    
    # Prescription type and number
    pdf.set_font('Arial', 'B', 12)
    tipo_names = {
        "CE": "CONSULTA EXTERNA",
        "EM": "EMERGENCIA", 
        "EH": "HOSPITALIZACIÓN"
    }
    pdf.cell(0, 8, f'TIPO: {tipo_names.get(tipo, tipo)}', 0, 1)
    pdf.cell(0, 8, f'NÚMERO: {data.get("numero", "N/A")}', 0, 1)
    pdf.cell(0, 8, f'FECHA: {data.get("fecha", datetime.now().strftime("%d/%m/%Y"))}', 0, 1)
    pdf.ln(3)
    
    # Health unit and service
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, f'Unidad de Salud: {data.get("unidad", "")}', 0, 1)
    pdf.cell(0, 6, f'Especialidad: {data.get("prescriptor_especialidad", data.get("servicio", ""))}', 0, 1)
pdf.cell(0, 6, f'Prescriptor: {data.get("prescriptor", "")}', 0, 1)
    pdf.ln(3)
    
    # Patient data section
    # (Modificado) incluir Fecha de Nacimiento si existe
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 8, 'DATOS DEL PACIENTE', 0, 1)
    pdf.set_font('Arial', '', 10)
    
    # Patient info in two columns
    pdf.cell(100, 6, f'Paciente: {data.get("paciente", "")}', 0, 0)
    pdf.cell(0, 6, f'CI: {data.get("ci", "")}', 0, 1)
    
    pdf.cell(50, 6, f'Historia Clínica: {data.get("hc", "")}', 0, 0)
    pdf.cell(30, 6, f'Sexo: {data.get("sexo", "")}', 0, 0)
    pdf.cell(30, 6, f'Edad: {data.get("edad", "")} años', 0, 0)
    pdf.cell(0, 6, f'Meses: {data.get("meses", "")}', 0, 1)
    
    pdf.cell(50, 6, f'Talla: {data.get("talla", "")} cm', 0, 0)
    pdf.cell(0, 6, f'Peso: {data.get("peso", "")} kg', 0, 1)
    pdf.ln(2)
    
    # Health status fields
    if data.get("actividad_fisica") or data.get("estado_enfermedad") or data.get("alergias"):
        pdf.cell(70, 6, f'Actividad Física: {data.get("actividad_fisica", "")}', 0, 0)
        pdf.cell(0, 6, f'Estado de Enfermedad: {data.get("estado_enfermedad", "")}', 0, 1)
        
        alergias_text = f'Alergias: {data.get("alergias", "")}'
        if data.get("alergias_especificar"):
            alergias_text += f' - {data.get("alergias_especificar", "")}'
        pdf.cell(0, 6, alergias_text, 0, 1)
        pdf.ln(2)
    
    # CIE-10 diagnosis
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 8, 'DIAGNÓSTICO', 0, 1)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, f'CIE-10: {data.get("cie", "")} - {data.get("cie_desc", "")}', 0, 1)
    pdf.ln(3)
    
    # Medications section
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 8, 'MEDICAMENTOS PRESCRITOS', 0, 1)
    pdf.set_font('Arial', '', 9)
    
    # Table column widths (adjusted to fit page width of 190mm)
    col_widths = [70, 20, 25, 25, 25, 25]  # Total: 190mm
    headers = ['Medicamento', 'Dosis', 'Frecuencia', 'Vía', 'Duración', 'Cantidad']
    
    # Draw table header
    pdf.set_fill_color(240, 240, 240)
    start_x = 10
    for i, (header, width) in enumerate(zip(headers, col_widths)):
        pdf.set_xy(start_x + sum(col_widths[:i]), pdf.get_y())
        pdf.cell(width, 8, header, 1, 0, 'C', True)
    pdf.ln(8)
    
    # Medications data with text wrapping
    medications = data.get("meds", [])
    pdf.set_fill_color(255, 255, 255)
    
    if medications:
        # Prepare data for multi-cell table
        med_data = []
        for med in medications:
            row = [
                str(med.get("nombre", "")),
                str(med.get("dosis", "")),
                str(med.get("frecuencia", "")),
                str(med.get("via", "")),
                str(med.get("duracion", "")),
                str(med.get("cantidad", ""))
            ]
            med_data.append(row)
        
        # Draw medications table with text wrapping
        pdf.multi_cell_table(med_data, col_widths, height=6)
    
    pdf.ln(5)
    
    # Instructions section
    if data.get("indicaciones"):
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 8, 'INDICACIONES / ADVERTENCIAS / RECOMENDACIONES', 0, 1)
        pdf.set_font('Arial', '', 10)
        
        # Split long text into multiple lines with proper wrapping
        indicaciones = str(data.get("indicaciones", ""))
        wrapped_lines = pdf.wrap_text(indicaciones, 180)  # 180mm width for text
        
        for line in wrapped_lines:
            pdf.cell(0, 6, line, 0, 1)
    
    pdf.ln(10)
    
    # Signature section
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, '_' * 50, 0, 1, 'C')
    pdf.cell(0, 6, 'Firma y Sello del Prescriptor', 0, 1, 'C')
    pdf.cell(0, 6, data.get("prescriptor", ""), 0, 1, 'C')
    
    # Save the PDF
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        pdf.output(output_path)
        return True
    except Exception as e:
        raise Exception(f"Error saving PDF: {str(e)}")



def build_indicaciones_pdf(output_path, data):
    """
    Genera un PDF únicamente con las INDICACIONES para entregar aparte.
    Incluye encabezado institucional, datos mínimos del paciente y del prescriptor.
    """
    class PDFInd(FPDF):
        def header(self):
            self.set_fill_color(240, 240, 240)
            self.rect(0, 0, 210, 18, 'F')
            self.set_font('Arial', 'B', 12)
            self.cell(0, 10, 'HOSPITAL BÁSICO DE CAYAMBE - INDICACIONES', 0, 1, 'C')
            self.ln(2)
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

    pdf = PDFInd()
    pdf.add_page()
    pdf.set_font('Arial', '', 10)

    pdf.cell(0, 6, f'Paciente: {data.get("paciente", "")}', 0, 1)
    if data.get('fecha_nacimiento'):
        pdf.cell(0, 6, f'Fecha de Nacimiento: {data.get("fecha_nacimiento", "")}', 0, 1)
    edad_str = f'{data.get("edad", "")} años {data.get("meses", "")} meses'
    pdf.cell(0, 6, f'Edad: {edad_str}', 0, 1)
    pdf.cell(0, 6, f'CI: {data.get("ci", "")}', 0, 1)
    pdf.cell(0, 6, f'Prescriptor: {data.get("prescriptor", "")}', 0, 1)
    pdf.ln(4)

    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 8, 'INDICACIONES', 0, 1)
    pdf.set_font('Arial', '', 10)

    indicaciones = str(data.get("indicaciones", "")) or "(Sin indicaciones)"
    # simple wrap using available wrap_text if present
    try:
        lines = pdf.wrap_text(indicaciones, 180)  # type: ignore
    except Exception:
        # naive wrap
        import textwrap as tw
        lines = tw.wrap(indicaciones, width=110)
    for line in lines:
        pdf.cell(0, 6, line, 0, 1)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    return output_path
