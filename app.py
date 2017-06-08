from flask import Flask, render_template, Response , request
from werkzeug import secure_filename
import time
import subprocess

# Initialize the Flask application
app = Flask(__name__)

# This is the path to the upload directory
app.config['UPLOAD_FOLDER'] = 'uploads/' #move it to skel folder and use dconf to set it as wallpaper in later stages

# These are the extension that we are accepting to be uploaded
app.config['ALLOWED_EXTENSIONS'] = set(['png', 'jpg', 'jpeg'])


@app.route('/')
def index():
	#Index page
	return render_template("index.html")

# Route that will process the file upload
@app.route('/upload', methods=['POST'])
def upload():
	# Get the name of the uploaded file
	file = request.files['file']
	# Check if the file is one of the allowed types/extensions
	if file and allowed_file(file.filename):
		# Make the filename safe, remove unsupported chars
		filename = secure_filename(file.filename)
		# Move the file form the temporal folder to
		# the upload folder we setup
		file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))


@app.route('/yield')
def output():
	def inner():
		proc = subprocess.Popen(

			['./script.sh'], #call something with a lot of output so we can see it

			shell=True,universal_newlines=True,
			stdout=subprocess.PIPE
		)

		for line in iter(proc.stdout.readline,''):
			time.sleep(1)  # Don't need this just shows the text streaming
			yield line.rstrip() + '<br/>\n'

	return Response(inner(), mimetype='text/html')  # text/html is required for most browsers to show th$

#Function to call meilix script on clicking the build button

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
