# Local development

Want to contribute? Great!

## Prerequisites
Fork meilix-generator and meilix onto your account. You need special permissions to test and deploy.

``` bash
# clone meilix repo
$ git clone https://github.com/<your_username>/meilix.git meilix

# clone meilix-generator into separate directory
$ git clone https://github.com/<your_username>/meilix-generator.git meilix-generator
```

Get started by installing the virtual environment
``` bash
$ sudo pip install virtualenv
```

`cd` into the cloned repository and start the virtual environment
``` bash
$ cd meilix-generator
$ virtualenv venv
```

Activate the virtual environment
``` bash
$ source venv/bin/activate
```

Install all dependencies(frameworks, templating...)
``` bash
$ sudo pip install -r requirements.txt
```


## Run locally

Adding application
``` bash
$ export FLASK_DEBUG=1 FLASK_APP=app.py
```

Run the application
``` bash
$ flask run
```

Now your app should be running on `http://127.0.0.0:5000`.

**Note:** Make sure to generate your own tokens and API keys. Refer to [my_token.md](my_token.md) for details.

_Look at [heroku installation](heroku.md) on how to test and deploy on Heroku_
