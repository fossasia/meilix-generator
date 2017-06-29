### Development

Want to contribute? Great!

# How to install the Meilix-Generator on local machine

## Deploying Locally

**Star** the repo and fork it and clone the forked one.

Open your favorite Terminal and run these commands.

Get started by installing the virtual environment
```sh
$ sudo pip install virtualenv
```

cd into the cloned repository and start the virtual environment
```sh
$ virtualenv venv
```

activate the virtual environment
```sh
$ source venv/bin/activate
```
#### Building for source
install the basic requirements
```sh
$ sudo pip install -r requirements.txt
```
adding application
```sh
$ export FLASK_DEBUG=1 FLASK_APP=app.py
```

run the application
```sh
$ flask run
```

Verify the deployment by navigating to your server address in your preferred browser.

```sh
127.0.0.1:5000
```

Note: see more [here](/docs/installation/my_token.md) about token and script

**Have an eye on the terminal to know about the process.**

*Look at [heroku installation](docs/installation/heroku.md) to test and deploy the build*
