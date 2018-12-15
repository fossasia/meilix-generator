import base64  # for encoding the script for variable

import os
import re
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug import secure_filename

# These are the extension that we are accepting to be uploaded
ALLOWED_EXTENSIONS_WALLPAPER = set(['png', 'jpg', 'jpeg'])
ALLOWED_EXTENSIONS_LOGO = set(['svg'])
ALLOWED_EXTENSIONS_DESKTOP = set(['gz','zip'])

#The name of the upload directories
UPLOAD_FOLDER = 'uploads/'
WALLPAPER_FOLDER  = 'wallpapers/'
LOGO_FOLDER = 'logos/'
ZIP_FOLDER = 'zip-archives/'

# Initialize the Flask application
app = Flask(__name__)

# This is the path to the upload directory
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['LOGO_FOLDER'] = LOGO_FOLDER
app.config['ZIP_FOLDER'] = ZIP_FOLDER
app.config['WALLPAPER_FOLDER'] = WALLPAPER_FOLDER

# The maximum file size
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024


def allowed_file(filename):
    # Check for allowed file extension
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS_WALLPAPER or ALLOWED_EXTENSIONS_LOGO or ALLOWED_EXTENSIONS_DESKTOP


def urlify(s):
    """Remove all non-word characters (everything except numbers and letters)"""
    s = re.sub(r"[^\w\s]", '', s).strip()
    # Replace all runs of whitespace with a single dash
    s = re.sub(r"\s+", '-', s)
    return s


@app.route("/", methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form['email']
        TRAVIS_TAG = request.form['TRAVIS_TAG']
        event_url = request.form['event_url']
        variables = {}
        for name, value in request.form.items():
          if name.startswith("GENERATOR_"):
            variables[name] = value
        wallpaper = request.files["desktop-wallpaper"]
        if wallpaper and allowed_file(wallpaper.filename):
            filename = secure_filename(wallpaper.filename)
            wallpaper.save(os.path.join(app.config['UPLOAD_FOLDER'] + app.config['WALLPAPER_FOLDER'], filename))
        logo = request.files["desktop-logo"]
        if logo and allowed_file(logo.filename):
            filename = secure_filename(logo.filename)
            logo.save(os.path.join(app.config['UPLOAD_FOLDER'] + app.config['LOGO_FOLDER'], filename))
        zipFiles = request.files["desktop-files"]
        if zipFiles and allowed_file(zipFiles.filename):
            filename = secure_filename(zipFiles.filename)
            zipFiles.save(os.path.join(app.config['UPLOAD_FOLDER'] + app.config['ZIP_FOLDER'], filename))
        if email != '' and TRAVIS_TAG != '':
            os.environ["email"] = email
            TRAVIS_TAG = urlify(TRAVIS_TAG)  # this will fix url issue
            os.environ["TRAVIS_TAG"] = TRAVIS_TAG
            os.environ["event_url"] = event_url
            with open('travis_script_1.sh', 'rb') as f:
                os.environ["TRAVIS_SCRIPT"] = str(base64.b64encode(f.read()))[1:]
            return redirect(url_for('output'))
    return render_template('index.html')


@app.route('/output')
def output():
    if os.environ['TRAVIS_TAG']:  # if TRAVIS_TAG have value it will proceed
        os.system('./script.sh')
        print ('/build called')
        return render_template('build.html')
    else:
        return redirect(url_for('index'))


# Function to call meilix script on clicking the build button

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


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
