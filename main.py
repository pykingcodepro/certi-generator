from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import os
import csv
import zipfile
from PIL import Image, ImageDraw, ImageFont
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from werkzeug.utils import secure_filename
import tempfile
import shutil
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create necessary directories
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
TEMPLATE_CONFIG_FOLDER = 'template_configs'  # New folder for template configurations
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMPLATE_CONFIG_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {
    'csv': {'csv'},
    'image': {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
}

def allowed_file(filename, file_type):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS[file_type]

class CertificateGenerator:
    def __init__(self, template_path, output_format='pdf'):
        self.template_path = template_path
        self.output_format = output_format.lower()  # Normalize format
        self.certificates = []
        app.logger.info(f"Initializing CertificateGenerator with format: {self.output_format}")
        
        # Load template configuration if it exists
        template_filename = os.path.basename(template_path)
        config_filename = secure_filename(f"{template_filename}.json")
        config_path = os.path.join(TEMPLATE_CONFIG_FOLDER, config_filename)
        
        self.template_config = None
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    self.template_config = json.load(f)
            except Exception as e:
                app.logger.error(f"Error loading template configuration: {e}")

    def parse_csv(self, csv_path):
        """Parse CSV file and return list of dictionaries"""
        data = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                for row in csv_reader:
                    # Clean up keys and values (remove whitespace)
                    cleaned_row = {}
                    for k, v in row.items():
                        clean_key = k.strip().lower()
                        clean_value = v.strip() if v else ''
                        cleaned_row[clean_key] = clean_value
                    
                    # Normalize name field - check for various name field variations
                    name_value = self.find_name_field(cleaned_row)
                    if name_value:
                        cleaned_row['name'] = name_value
                    
                    data.append(cleaned_row)
            return data
        except Exception as e:
            print(f"Error parsing CSV: {e}")
            return []
    
    def find_name_field(self, row):
        """Find name field regardless of case or whitespace"""
        # Common variations of 'name' field
        name_variations = [
            'name', 'names', 'full_name', 'fullname', 'full name',
            'student_name', 'studentname', 'student name',
            'participant_name', 'participantname', 'participant name',
            'recipient_name', 'recipientname', 'recipient name',
            'person_name', 'personname', 'person name'
        ]
        
        # Check each variation
        for variation in name_variations:
            if variation in row and row[variation] and row[variation].strip():
                return row[variation].strip()
        
        # If no standard name field found, check if any key contains 'name'
        for key, value in row.items():
            if 'name' in key and value and value.strip():
                return value.strip()
        
        return None
    
    def create_certificate_image(self, data_row):
        """Create certificate image with data overlaid on template"""
        try:
            # Check if name field exists (required field)
            if 'name' not in data_row or not data_row['name']:
                print(f"Warning: Missing or empty name field in row: {data_row}")
                return None
            
            # Open template image
            template = Image.open(self.template_path)
            template = template.copy()  # Make a copy to avoid modifying original
            
            # Create drawing object
            draw = ImageDraw.Draw(template)
            
            # Get image dimensions
            width, height = template.size
            
            # Use template configuration if available, otherwise use defaults
            if self.template_config:
                font_size = int(self.template_config['font_size'])
                font_family = self.template_config['font_family']
                text_color = self.template_config['text_color']
                text_x = float(self.template_config['text_position']['x']) * width
                text_y = float(self.template_config['text_position']['y']) * height
            else:
                font_size = 48
                font_family = "Arial"
                text_color = "#000000"
                text_x = width // 2
                text_y = height // 2 - 50
            
            # Try to load the configured font
            try:
                font = ImageFont.truetype(f"{font_family}.ttf", font_size)
            except:
                # Fallback fonts if the configured one is not available
                for fallback in ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]:
                    try:
                        font = ImageFont.truetype(fallback, font_size)
                        break
                    except:
                        continue
                else:
                    font = ImageFont.load_default()
            
            # Convert hex color to RGB
            if text_color.startswith('#'):
                text_color = tuple(int(text_color[i:i+2], 16) for i in (1, 3, 5))
            
            # Add text to certificate
            text = str(data_row['name']).strip()
            
            # Center text
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = text_x - text_width // 2
            y = text_y - text_height // 2
            
            draw.text((x, y), text, font=font, fill=text_color)
            
            return template
            
        except Exception as e:
            print(f"Error creating certificate image: {e}")
            return None
    
    def get_field_value(self, data_row, field_name):
        """Get field value with case-insensitive matching and whitespace handling"""
        # Direct match first
        if field_name in data_row and data_row[field_name]:
            return data_row[field_name]
        
        # For non-name fields, try variations
        if field_name != 'name':
            field_variations = {
                'course': ['course', 'courses', 'program', 'subject', 'class', 'training'],
                'date': ['date', 'completion_date', 'issue_date', 'awarded_date', 'finished_date'],
                'grade': ['grade', 'score', 'mark', 'result', 'performance', 'rating'],
                'organization': ['organization', 'organisation', 'institute', 'school', 'company', 'academy'],
                'certificate_id': ['certificate_id', 'cert_id', 'id', 'serial', 'number', 'certificate_number']
            }
            
            if field_name in field_variations:
                for variation in field_variations[field_name]:
                    if variation in data_row and data_row[variation]:
                        return data_row[variation]
        return None
    
    def image_to_pdf(self, image):
        """Convert PIL Image to PDF bytes"""
        try:
            app.logger.info("Converting image to PDF")
            pdf_buffer = io.BytesIO()
            
            # Convert image to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Save directly as PDF using PIL
            image.save(pdf_buffer, format='PDF', resolution=100.0)
            pdf_buffer.seek(0)
            
            app.logger.info("Image to PDF conversion successful")
            return pdf_buffer.getvalue()
            
        except Exception as e:
            app.logger.error(f"Error converting image to PDF: {e}")
            return None
    
    def generate_certificates(self, csv_path):
        """Generate all certificates from CSV data"""
        data = self.parse_csv(csv_path)
        if not data:
            return []
        
        certificates = []
        app.logger.info(f"Generating certificates for {len(data)} entries")
        
        for i, row in enumerate(data):
            # Create certificate image
            cert_image = self.create_certificate_image(row)
            if cert_image is None:
                continue
            
            # Generate filename using name (which is guaranteed to exist)
            name = row.get('name', f'Certificate_{i+1}').strip().replace(' ', '_')
            if not name:  # Fallback if name is empty after stripping
                name = f'Certificate_{i+1}'
            filename = secure_filename(f"{name}_certificate")
            
            # Always convert to PDF for single_pdf option
            if self.output_format == 'pdf':
                app.logger.info(f"Converting certificate {i+1} to PDF")
                # Convert to PDF
                pdf_data = self.image_to_pdf(cert_image)
                if pdf_data:
                    certificates.append({
                        'filename': f"{filename}.pdf",
                        'data': pdf_data,
                        'type': 'pdf'
                    })
                    app.logger.info(f"PDF conversion successful for {filename}")
                else:
                    app.logger.error(f"PDF conversion failed for {filename}")
            else:  # image format
                app.logger.info(f"Saving certificate {i+1} as PNG")
                # Save as PNG
                img_buffer = io.BytesIO()
                cert_image.save(img_buffer, format='PNG')
                certificates.append({
                    'filename': f"{filename}.png",
                    'data': img_buffer.getvalue(),
                    'type': 'image'
                })
        
        app.logger.info(f"Generated {len(certificates)} certificates")
        return certificates

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_certificates():
    try:
        # Check if files are provided
        if 'csv_file' not in request.files or 'template_file' not in request.files:
            return 'Please provide both CSV and template files', 400
        
        csv_file = request.files['csv_file']
        template_file = request.files['template_file']
        output_type = request.form.get('output_type', 'pdf')
        
        app.logger.info(f"Requested output type: {output_type}")
        
        # Validate files
        if csv_file.filename == '' or template_file.filename == '':
            return 'Please select both files', 400
        
        if not (allowed_file(csv_file.filename, 'csv') and 
                allowed_file(template_file.filename, 'image')):
            return 'Invalid file types. Please upload CSV and image files.', 400
        
        # Save uploaded files
        csv_filename = secure_filename(csv_file.filename)
        template_filename = secure_filename(template_file.filename)
        
        csv_path = os.path.join(UPLOAD_FOLDER, csv_filename)
        template_path = os.path.join(UPLOAD_FOLDER, template_filename)
        
        csv_file.save(csv_path)
        template_file.save(template_path)
        
        try:
            # Generate certificates based on output type
            generator = CertificateGenerator(template_path, output_type)
            certificates = generator.generate_certificates(csv_path)
            
            if not certificates:
                return 'No certificates could be generated. Please check your CSV file format.', 400
            
            app.logger.info(f"Generated {len(certificates)} certificates")
            for cert in certificates:
                app.logger.info(f"Certificate type: {cert['type']}")
            
            # Clean up uploaded files
            os.remove(csv_path)
            os.remove(template_path)
            
            # If multiple files, create ZIP
            if len(certificates) > 1:
                return send_zip_file(certificates)
            
            # Single file
            else:
                cert = certificates[0]
                return send_file(
                    io.BytesIO(cert['data']),
                    as_attachment=True,
                    download_name=cert['filename'],
                    mimetype='application/pdf' if cert['type'] == 'pdf' else 'image/png'
                )
                
        finally:
            # Ensure files are cleaned up even if an error occurs
            try:
                if os.path.exists(csv_path):
                    os.remove(csv_path)
                if os.path.exists(template_path):
                    os.remove(template_path)
            except:
                pass
            
    except Exception as e:
        app.logger.error(f'Error generating certificates: {str(e)}')
        return f'An error occurred while generating certificates: {str(e)}', 500

def send_zip_file(certificates):
    """Create ZIP file with all certificates"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for cert in certificates:
            zip_file.writestr(cert['filename'], cert['data'])
    
    zip_buffer.seek(0)
    
    return send_file(
        zip_buffer,
        as_attachment=True,
        download_name=f'certificates_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
        mimetype='application/zip'
    )

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))

@app.route('/template-editor', methods=['GET', 'POST'])
def template_editor():
    if request.method == 'POST':
        if 'template_file' not in request.files:
            flash('Please provide a template file')
            return redirect(url_for('template_editor'))
        
        template_file = request.files['template_file']
        if template_file.filename == '':
            flash('No selected file')
            return redirect(url_for('template_editor'))
            
        if not allowed_file(template_file.filename, 'image'):
            flash('Invalid file type. Please upload an image file.')
            return redirect(url_for('template_editor'))
            
        # Save uploaded template
        template_filename = secure_filename(template_file.filename)
        template_path = os.path.join(UPLOAD_FOLDER, template_filename)
        template_file.save(template_path)
        
        # Return template info for the editor
        return render_template('template_editor.html', 
                            template_filename=template_filename)
    
    return render_template('template_editor.html')

@app.route('/save-template-config', methods=['POST'])
def save_template_config():
    try:
        config_data = request.json
        template_filename = config_data.get('template_filename')
        
        if not template_filename:
            return {'error': 'No template filename provided'}, 400
            
        config_filename = secure_filename(f"{template_filename}.json")
        config_path = os.path.join(TEMPLATE_CONFIG_FOLDER, config_filename)
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
            
        return {'success': True, 'message': 'Configuration saved successfully'}
    except Exception as e:
        return {'error': str(e)}, 500

if __name__ == '__main__':
    app.run(debug=True)