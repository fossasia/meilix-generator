Dropbox Core SDK for Python
===========================

A Python library for Dropbox's HTTP-based Core and Datastore APIs.

- https://www.dropbox.com/developers/core/docs
- https://www.dropbox.com/developers/datastore/docs

Setup
-----

You can install this package using ``pip``::

   $ pip install dropbox

Getting a Dropbox API key
-------------------------

You need a Dropbox API key to make API requests.

- Go to https://dropbox.com/developers/apps.
- If you've already registered an app, click on the "Options" link to see the
  app's API key and secret.
- Otherwise, click "Create an app" to register an app. Choose "Dropbox API"
  with datastore and/or file permissions depending on your needs.
  See https://www.dropbox.com/developers/reference#app-permissions.

Using the Dropbox API
---------------------

Full documentation:

- https://www.dropbox.com/developers/core/docs
- https://www.dropbox.com/developers/datastore/docs

Before your app can access a Dropbox user's files, the user must authorize your
application using OAuth 2.  Successfully completing this authorization flow
gives you an "access token" for the user's Dropbox account, which grants you the
ability to make Dropbox API calls to access their files.

- Authorization example for a web app: example/flask_app/
- Authorization example for a command-line tool:
  https://www.dropbox.com/developers/core/start/python

Once you have an access token, create a DropboxClient instance and start making
API calls.

You only need to perform the authorization process once per user.  Once you have
an access token for a user, save it somewhere persistent, like in a database.
The next time that user visits your app, you can skip the authorization process
and go straight to making API calls.

Running the Examples
--------------------

There are example programs in the "example" folder.  Before you can run an
example, you need to edit the ".py" file and put your Dropbox API app key and
secret in the "APP_KEY" and "APP_SECRET" constants.
