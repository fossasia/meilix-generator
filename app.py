from flask import Flask, render_template, Response
import time
import subprocess
import sys, os

# cloning meilix code
#os.system("git clone https://github.com/fossasia/meilix.git")

app = Flask(__name__)


@app.route('/')
def index():
	#Index page
	return render_template("index.html")

@app.route('/oauth')
def dropbox():
call(['bash', 'test.sh'])
call(['ls','-l'])

@app.route('/yield')
def output():
	def inner():
		proc = subprocess.Popen(
			['./script.sh'],             #call something with a lot of output so we can see it
			shell=True,universal_newlines=True,
			stdout=subprocess.PIPE
		)

		for line in iter(proc.stdout.readline,''):
			time.sleep(1)                           # Don't need this just shows the text streaming
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
