import base64  # for encoding the script for variable

import os
import re
import build
import json
from flask import Flask, flash, render_template, request, redirect, url_for, send_from_directory
from werkzeug import secure_filename
import requests


# These are the extension that we are accepting to be uploaded
ALLOWED_EXTENSIONS_WALLPAPERS = set(['png', 'jpg', 'jpeg'])
ALLOWED_EXTENSIONS_LOGO = set(['svg'])
ALLOWED_EXTENSIONS_ZIP = set(['gz','zip'])

#The name of the upload directories
UPLOAD_FOLDER = 'uploads/'
WALLPAPER_FOLDER  = 'wallpapers/'
LOGO_FOLDER = 'logos/'
ZIP_FOLDER = 'zip-archives/'

# Initialize the Flask application
app = Flask(__name__)

# Initializing flask secret key using the environment variable "secret_key"
app.secret_key = os.environ.get('secret_key', 'z528&^FJjhd_t2bxc#$2').encode()

# This is the path to the upload directory
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['LOGO_FOLDER'] = LOGO_FOLDER
app.config['ZIP_FOLDER'] = ZIP_FOLDER
app.config['WALLPAPER_FOLDER'] = WALLPAPER_FOLDER

# The maximum file size
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
flag = True

def allowed_wallpapers(filename):
    # Check for allowed file extension for wallpapers
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS_WALLPAPERS

def allowed_logos(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS_LOGO

def allowed_zip_files(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS_ZIP

def urlify(s):
    """Remove all non-word characters (everything except numbers and letters)"""
    s = re.sub(r"[^\w\s]", '', s).strip()
    # Replace all runs of whitespace with a single dash
    s = re.sub(r"\s+", '-', s)
    return s

def upload_wallpaper(wallpaper):
    url=""
    if wallpaper:
        if allowed_wallpapers(wallpaper.filename):
            filename = secure_filename(wallpaper.filename)
            try:
                # Uploading wallpaper to transfer.sh
                response = requests.post('https://transfer.sh', files= {'file': (filename, wallpaper),})
                url = response.text
            except:
                try:
                    print("upload failed(transfer.sh) \n retrying(0x0.st)")
                    wallpaper.seek(0)
                    response = requests.post('https://0x0.st', files= {'file': (filename, wallpaper),})
                    url = response.text
                except:
                    # Saving wallpaper to host
                    wallpaper.seek(0)
                    wallpaper.save(os.path.join(app.config['UPLOAD_FOLDER'] + app.config['WALLPAPER_FOLDER'], filename))
                    os.rename(UPLOAD_FOLDER + WALLPAPER_FOLDER + filename, UPLOAD_FOLDER + WALLPAPER_FOLDER + 'wallpaper')
                    url = "https://meilix-generator.herokuapp.com/uploads/wallpapers/wallpapers"
            print(url)
        else:
            flash('Wallpaper not saved, extension not allowed')
            global flag
            flag = False
    return(url)

def upload_logo(logo):
    url=""
    if logo:
        if allowed_logos(logo.filename):
            filename = secure_filename(logo.filename)
            try:
                # Uploading logo to transfer.sh
                response = requests.post('https://transfer.sh', files= {'file': (filename, logo),})
                url = response.text
            except:
                try:
                    print("upload failed(transfer.sh) \n retrying(0x0.st)")
                    wallpaper.seek(0)
                    response = requests.post('https://0x0.st', files= {'file': (filename, logo),})
                    url = response.text
                except:
                    # Saving logo to host
                    wallpaper.seek(0)
                    logo.save(os.path.join(app.config['UPLOAD_FOLDER'] + app.config['LOGO_FOLDER'], filename))
                    os.rename(UPLOAD_FOLDER + LOGO_FOLDER + filename, UPLOAD_FOLDER + LOGO_FOLDER + 'logo')
                    url = "https://meilix-generator.herokuapp.com/uploads/logos/logo"
            print(url)
        else:
            flash('Logo not saved, extension not allowed')
            global flag
            flag = False
    return(url)

def upload_zip(zipFiles):
    if zipFiles:
        if allowed_zip_files(zipFiles.filename):
            filename = secure_filename(zipFiles.filename)
            zipFiles.save(os.path.join(app.config['UPLOAD_FOLDER'] + app.config['ZIP_FOLDER'], filename))
            os.rename(UPLOAD_FOLDER + ZIP_FOLDER + filename, UPLOAD_FOLDER + ZIP_FOLDER + 'zip-file')
        else:
            flash('Zip File not saved, extension not allowed')
            global flag
            flag = False

@app.route("/", methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form['email']
        TRAVIS_TAG = request.form['TRAVIS_TAG']
        event_url = request.form['event_url']
        variables = {}
        features = {}
        processor = "amd64" # This will fixe build failure when 32bit is not chosen
        theme = "light"
        for name, value in request.form.items():
            if name == "processor":
                processor = value
            if name == "theme":
                theme = value
            if name.startswith("INSTALL_"):
                variables[name] = value
            if name.startswith("SWITCH_ON_"):
                features[name] = value
        recipe = json.dumps(variables, ensure_ascii=False) # Dumping the generator-packages into a JSON array
        feature = json.dumps(features, ensure_ascii=False) # Dumping the chosen features into a JSON objects
        INSTALL = request.form.getlist('INSTALL')
        wallpaper = request.files["desktop-wallpaper"]
        wallpaper_url = upload_wallpaper(wallpaper)
        logo = request.files["desktop-logo"]
        logo_url = upload_logo(logo)
        zipFiles = request.files["desktop-files"]
        upload_zip(zipFiles)
        if email != '' and TRAVIS_TAG != '':
            os.environ["email"] = email
            TRAVIS_TAG = urlify(TRAVIS_TAG)  # this will fix url issue
            os.environ["TRAVIS_TAG"] = TRAVIS_TAG
            os.environ["event_url"] = event_url
            os.environ["recipe"] = recipe
            os.environ["processor"] = processor
            os.environ["feature"] = feature
            os.environ["INSTALL"] = INSTALL
            os.environ["wallpaper_url"] = wallpaper_url
            os.environ["logo_url"] = logo_url
            os.environ["theme"] = theme
            with open('travis_script_1.sh', 'rb') as f:
                os.environ["TRAVIS_SCRIPT"] = str(base64.b64encode(f.read()))[1:]
            return redirect(url_for('output'))
    return render_template('index.html')


@app.route('/output')
def output():
    if flag:
        if os.environ['TRAVIS_TAG']:  # if TRAVIS_TAG have value it will proceed
            trigger_code = build.send_trigger_request(os.environ['email'], os.environ['TRAVIS_TAG'], os.environ['event_url'],os.environ['TRAVIS_SCRIPT'], os.environ['recipe'], os.environ['processor'], os.environ['feature'], os.environ['INSTALL'], os.environ['wallpaper_url'], os.environ["logo_url"], os.environ['theme'])
            if trigger_code != 202:
                flash('Trigger failed, response code {}'.format(trigger_code)) #Display error if trigger fails
            return render_template('build.html')
        else:
            return redirect(url_for('index'))
    else:
        return render_template('build.html')

# Function to call meilix script on clicking the build button

@app.route('/uploads/wallpapers/<filename>')
def uploaded_wallpaper(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'] + app.config['WALLPAPER_FOLDER'], filename)

@app.route('/uploads/logos/<filename>')
def uploaded_logo(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'] + app.config['LOGO_FOLDER'], filename)

@app.route('/uploads/zip-archives/<filename>')
def uploaded_zip(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'] + app.config['ZIP_FOLDER'], filename)

# Return a custom 404 error.
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html')


@app.errorhandler(500)
def application_error(e):
    # Return a custom 500 error.
    return 'Sorry, unexpected error: {}'.format(e), 500


if __name__ == '__main__':
    app.run()
