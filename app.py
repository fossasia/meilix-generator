import os
from flask import Flask, render_template, Response ,request ,redirect ,url_for ,send_from_directory

from werkzeug import secure_filename
import re

import datetime

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
# These are the extension that we are accepting to be uploaded
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])
UPLOAD_FOLDER = 'uploads/'
# Initialize the Flask application
app = Flask(__name__)

# This is the path to the upload directory
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
        #Check for allowed file extension
	return '.' in filename and \
			filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

def urlify(s):
    """Remove all non-word characters (everything except numbers and letters)"""
    s = re.sub(r"[^\w\s]", '', s).strip()
    #Replace all runs of whitespace with a single dash
    s = re.sub(r"\s+", '-', s)
    return s

@app.route("/", methods=['GET', 'POST'])
def index():
	if request.method == 'POST':
		email = request.form['email']
		TRAVIS_TAG = request.form['TRAVIS_TAG']
		file = request.files['file']
		if file and allowed_file(file.filename):
			filename = secure_filename(file.filename)
			file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
			os.rename(UPLOAD_FOLDER + filename, UPLOAD_FOLDER+'wallpaper')
			filename = 'wallpaper'
			if email != '' and TRAVIS_TAG != '':
				os.environ["email"] = email
				TRAVIS_TAG = urlify(TRAVIS_TAG)#this will fix url issue
				os.environ["TRAVIS_TAG"] = TRAVIS_TAG
				return redirect(url_for('test_page'))
	return render_template('index.html')

def status():
    tag = os.environ["TRAVIS_TAG"]
    date = datetime.datetime.now().strftime('%Y%m%d')
    url = "https://github.com/xeon-zolt/meilix/releases/download/"+tag+"/meilix-zesty-"+date+"-i386.iso"
    req = Request(url)
    try:
        response = urlopen(req)
    except HTTPError as e:
        return('Building Your Iso')
    except URLError as e:
        return('We failed to reach the server.')
    else:
        return('Build Sucessful : ' + url)


@app.route('/now')
def status_url():
	return (status())

#Function to call meilix script on clicking the build button
@app.route('/test')
def test_page():
	if os.environ['TRAVIS_TAG']:#if TRAVIS_TAG have value it will proceed
		os.system('./script.sh')
		print ('/test called')
		return send_from_directory('static','test.html')
	else:
		return redirect(url_for('index'))

	return Response(inner())  # text/html is required for most browsers to show th$



@app.route('/uploads/<filename>')
def uploaded_file(filename):
	return send_from_directory(app.config['UPLOAD_FOLDER'],filename)

@app.route('/about')
def about():
	#About page
	return render_template("about.html")

#Return a custom 404 error.
@app.errorhandler(404)
def page_not_found(e):
	return 'Sorry, unexpected error: {}'.format(e), 404

@app.errorhandler(500)
def application_error(e):
	#Return a custom 500 error.
	return 'Sorry, unexpected error: {}'.format(e), 500

if __name__ == '__main__':
	app.run()
