import os
from flask import Flask, render_template, Response ,request ,redirect ,url_for ,send_from_directory

from werkzeug import secure_filename
import time
import subprocess
import re
# These are the extension that we are accepting to be uploaded
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])
UPLOAD_FOLDER = 'uploads/'
# Initialize the Flask application
app = Flask(__name__)

# This is the path to the upload directory
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
	return '.' in filename and \
			filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

def urlify(s):
     # Remove all non-word characters (everything except numbers and letters)
     s = re.sub(r"[^\w\s]", '', s).strip()
     # Replace all runs of whitespace with a single dash
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
				return redirect(url_for('output'))
	return render_template('index.html')

@app.route('/yield')
def output():
	if os.environ['TRAVIS_TAG']: #if TRAVIS_TAG have value it will proceed
		def inner():
			proc = subprocess.Popen(

				['./script.sh'],             #call something with a lot of output so we can see it

				shell=True,universal_newlines=True,
				stdout=subprocess.PIPE
			)

			for line in iter(proc.stdout.readline,''):
				time.sleep(1)  # Don't need this just shows the text streaming
				yield line.rstrip() + '<br/>\n'

	else:
		return redirect(url_for('index'))
	return Response(inner(), mimetype='text/html')  # text/html is required for most browsers to show th$

#Function to call meilix script on clicking the build button

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
