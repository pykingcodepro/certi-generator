from flask import *
import csv
import io
import os
import threading
import time
from PIL import Image, ImageDraw, ImageFont
import zipfile

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Add a secret key for session management and flash messages

ALLOWED_EXTENSIONS = ['csv']
TEMPLATE_PATH = "./static/img/template.png"
OUTPUT_IMAGES_PATH = './static/output/img'
OUTPUT_PDF_PATH = './static/output/pdf/output.pdf'
OUTPUT_ZIP_PATH = './static/output/zip'
FONT_PATH = './static/font/Roboto-Regular.ttf'
FONT_SIZE = 60
FONT_COLOR = (0, 0, 0)
TEXT_POSITION = (700, 600)


def zip_images(image_folder, output_folder=OUTPUT_ZIP_PATH, zip_name="certificates.zip", extensions=(".jpg", ".png")):
    # Ensure the output folder exists
    os.makedirs(output_folder, exist_ok=True)
    
    # Full path for the zip file
    zip_path = os.path.join(output_folder, zip_name)

    # Create the zip
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in os.listdir(image_folder):
            if file.lower().endswith(extensions):
                file_path = os.path.join(image_folder, file)
                zipf.write(file_path, arcname=file)  # arcname keeps the file name only in zip

def clear_image_folder(folder_path, extensions=['.jpg']):
    for filename in os.listdir(folder_path):
        if any(filename.lower().endswith(ext) for ext in extensions):
            file_path = os.path.join(folder_path, filename)
            try:
                os.remove(file_path)
                print(f"Deleted {file_path}")
            except Exception as e:
                print(f"Could not delete {file_path}: {e}")

def convertToPDF():

    # Load all images
    image_files = [f for f in os.listdir(OUTPUT_IMAGES_PATH) if f.endswith('.jpg')]
    image_files.sort()

    # Open images
    images = [Image.open(os.path.join(OUTPUT_IMAGES_PATH, file)).convert("RGB") for file in image_files]

    # Save as a single PDF
    if images:
        images[0].save(OUTPUT_PDF_PATH, format='pdf', save_all=True, append_images=images[1:])
        print(f"Combined PDF saved to {OUTPUT_PDF_PATH}")
    else:
        print("No images found to combine.")


def generateCertifcates(data):
    # This function generates certificates based on the provided data
    print(data.keys())
    
    #Load the template image
    template = Image.open(TEMPLATE_PATH).convert("RGB")

    #Load the Drawing context
    draw = ImageDraw.Draw(template)

    #Load the font
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

    draw.text(TEXT_POSITION, data['Name'], font=font, fill=FONT_COLOR)

    output_file = f"{OUTPUT_IMAGES_PATH}/{data['Name'].replace(' ', '_')}_certificate.jpg"
    template.save(output_file)
    # print(f"Certificate saved to {output_file}")
    return 1


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash("No File Part in the form")
            return redirect(url_for('index'))
        
        file = request.files['file']
        if file.filename == '':
            flash("No File selected.")
            return redirect(url_for('index'))
        
        if file.filename.split('.')[-1] not in ALLOWED_EXTENSIONS:
            flash("Invalid File Type. Only use csv files", category="error")
            return redirect(url_for('index'))
        
        # Read the uploaded CSV file content and convert to list of dicts
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        data_list = [row for row in csv_input]
        # print(data_list)
        if "Name" not in data_list[0].keys() or "Date" not in data_list[0].keys() or "Event" not in data_list[0].keys():
            flash("Error in structure of CSV file.\n It should have only Name, Event and Date columns")
            return redirect(url_for('index'))
        
        time1 = time.perf_counter()
        thread_list = []
        for data in data_list:
            t = threading.Thread(target=generateCertifcates, args=[data])
            thread_list.append(t)
            t.start()
        for t in thread_list:
            t.join()
        time2 = time.perf_counter()
        print(f"Time taken: {time2-time1} seconds")
        print(f"Total certificate generated: {len(data_list)}")
        print(request.form["outputType"])
        if request.form["outputType"] == 1:
            convertToPDF()
            clear_image_folder(OUTPUT_IMAGES_PATH)
            return send_file(OUTPUT_PDF_PATH, as_attachment=True)
        else:
            zip_images(OUTPUT_IMAGES_PATH)
            clear_image_folder(OUTPUT_IMAGES_PATH)
            return send_file(OUTPUT_ZIP_PATH + '/certificates.zip', as_attachment=True)
    
    # GET method part
    return render_template('index.html')

if __name__ == '__main__':
    app.run()
